"""Small, testable interface to the Facer kernel character devices."""

from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
import errno
import fcntl
import os
from pathlib import Path
import stat
import threading
from typing import Dict, Iterable, Tuple


DYNAMIC_DEVICE = Path("/dev/acer-gkbbl-0")
STATIC_DEVICE = Path("/dev/acer-gkbbl-static-0")


@dataclass(frozen=True)
class ModeSpec:
    index: int
    name: str
    caption: str
    uses_color: bool
    uses_speed: bool
    uses_direction: bool
    uses_zones: bool = False


MODES: Tuple[ModeSpec, ...] = (
    ModeSpec(0, "Статичный", "Ровный цвет", True, False, False, True),
    ModeSpec(1, "Дыхание", "Мягкая пульсация", True, True, False),
    ModeSpec(2, "Неон", "Цветовой поток", False, True, False),
    ModeSpec(3, "Волна", "Радуга по зонам", False, True, True),
    ModeSpec(4, "Перелив", "Смена оттенков", True, True, True),
    ModeSpec(5, "Импульс", "Пульс из центра", True, True, False),
)
MODE_BY_INDEX: Dict[int, ModeSpec] = {mode.index: mode for mode in MODES}

SOFTWARE_EFFECTS = frozenset(("", "aurora", "comet", "palette"))
DEFAULT_PALETTE: Tuple[Tuple[int, int, int], ...] = (
    (145, 55, 255),
    (45, 210, 255),
    (255, 55, 180),
    (255, 174, 55),
)


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _normalize_palette(value) -> Tuple[Tuple[int, int, int], ...]:
    """Return a JSON-friendly palette in the firmware RGB range.

    Settings are user-editable JSON, so malformed colors are ignored rather
    than preventing the application from starting.  A palette needs at least
    two usable colors to describe a transition; otherwise the safe built-in
    palette is restored.
    """
    if isinstance(value, (str, bytes)):
        return DEFAULT_PALETTE
    try:
        colors = iter(value)
    except TypeError:
        return DEFAULT_PALETTE

    normalized = []
    for color in colors:
        if len(normalized) == 8:
            break
        if isinstance(color, (str, bytes)):
            continue
        try:
            components = tuple(color)
            if len(components) != 3:
                continue
            normalized.append(tuple(_clamp(component, 0, 255) for component in components))
        except (TypeError, ValueError, OverflowError):
            continue
    if len(normalized) < 2:
        return DEFAULT_PALETTE
    return tuple(normalized)


def _normalize_zone_colors(
    value, fallback: Tuple[int, int, int]
) -> Tuple[Tuple[int, int, int], ...]:
    """Return exactly one safe RGB color for each physical keyboard zone."""

    fallback = tuple(_clamp(component, 0, 255) for component in fallback)
    if isinstance(value, (str, bytes)) or value is None:
        items = ()
    else:
        try:
            items = tuple(value)
        except TypeError:
            items = ()

    colors = []
    for index in range(4):
        if index >= len(items) or isinstance(items[index], (str, bytes)):
            colors.append(fallback)
            continue
        try:
            components = tuple(items[index])
            if len(components) != 3:
                raise ValueError
            colors.append(
                tuple(_clamp(component, 0, 255) for component in components)
            )
        except (TypeError, ValueError, OverflowError):
            colors.append(fallback)
    return tuple(colors)


@dataclass(frozen=True)
class LightingState:
    mode: int = 0
    red: int = 145
    green: int = 55
    blue: int = 255
    brightness: int = 80
    speed: int = 4
    direction: int = 1
    zones: Tuple[int, ...] = (1, 2, 3, 4)
    software_effect: str = ""
    palette: Tuple[Tuple[int, int, int], ...] = DEFAULT_PALETTE
    zone_colors: Tuple[Tuple[int, int, int], ...] = ()

    def normalized(self) -> "LightingState":
        mode = self.mode if self.mode in MODE_BY_INDEX else 0
        red = _clamp(self.red, 0, 255)
        green = _clamp(self.green, 0, 255)
        blue = _clamp(self.blue, 0, 255)
        zones = tuple(sorted({int(zone) for zone in self.zones if 1 <= int(zone) <= 4}))
        if not zones:
            zones = (1, 2, 3, 4)
        software_effect = (
            self.software_effect
            if isinstance(self.software_effect, str)
            and self.software_effect in SOFTWARE_EFFECTS
            else ""
        )
        palette = _normalize_palette(self.palette)
        zone_source = self.zone_colors
        try:
            zone_source_is_empty = len(zone_source) == 0
        except TypeError:
            zone_source_is_empty = True
        # Profiles created before per-zone colors already stored the four
        # Palette-effect colors in ``palette``.  Preserve them transparently.
        if zone_source_is_empty and software_effect == "palette":
            zone_source = palette[:4]
        return replace(
            self,
            mode=mode,
            red=red,
            green=green,
            blue=blue,
            brightness=_clamp(self.brightness, 0, 100),
            speed=_clamp(self.speed, 0, 9),
            direction=1 if int(self.direction) != 2 else 2,
            zones=zones,
            software_effect=software_effect,
            palette=palette,
            zone_colors=_normalize_zone_colors(zone_source, (red, green, blue)),
        )

    def to_dict(self) -> dict:
        data = asdict(self.normalized())
        data["zones"] = list(data["zones"])
        data["palette"] = [list(color) for color in data["palette"]]
        data["zone_colors"] = [list(color) for color in data["zone_colors"]]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "LightingState":
        if not isinstance(data, dict):
            return cls().normalized()
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        clean = {key: value for key, value in data.items() if key in allowed}
        if "zones" in clean:
            try:
                clean["zones"] = tuple(clean["zones"])
            except TypeError:
                clean.pop("zones")
        return cls(**clean).normalized()


@dataclass(frozen=True)
class RGBColor:
    """One firmware-safe RGB color."""

    red: int
    green: int
    blue: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "red", _clamp(self.red, 0, 255))
        object.__setattr__(self, "green", _clamp(self.green, 0, 255))
        object.__setattr__(self, "blue", _clamp(self.blue, 0, 255))

    @classmethod
    def from_value(cls, color: Iterable[int]) -> "RGBColor":
        if isinstance(color, cls):
            return color
        try:
            components = tuple(color)
        except TypeError as error:
            raise ValueError("RGB color must contain exactly three components") from error
        if len(components) != 3:
            raise ValueError("RGB color must contain exactly three components")
        return cls(*components)

    def as_tuple(self) -> Tuple[int, int, int]:
        return self.red, self.green, self.blue


@dataclass(frozen=True)
class SoftwareFrame:
    """A complete software-rendered frame for the four physical zones."""

    zones: Tuple[RGBColor, RGBColor, RGBColor, RGBColor]

    def __post_init__(self) -> None:
        try:
            zones = tuple(RGBColor.from_value(color) for color in self.zones)
        except TypeError as error:
            raise ValueError("Software frame must contain exactly four zones") from error
        if len(zones) != 4:
            raise ValueError("Software frame must contain exactly four zones")
        object.__setattr__(self, "zones", zones)

    @classmethod
    def solid(cls, color: Iterable[int]) -> "SoftwareFrame":
        normalized = RGBColor.from_value(color)
        return cls((normalized, normalized, normalized, normalized))


class FacerError(RuntimeError):
    """Base class for actionable device errors."""


class DeviceMissingError(FacerError):
    pass


class DevicePermissionError(FacerError):
    pass


class DeviceWriteError(FacerError):
    pass


class SoftwareModeInactiveError(FacerError):
    pass


def build_dynamic_payload(state: LightingState, brightness=None) -> bytes:
    state = state.normalized()
    spec = MODE_BY_INDEX[state.mode]
    payload = bytearray(16)
    payload[0] = state.mode
    payload[1] = state.speed
    payload[2] = state.brightness if brightness is None else _clamp(brightness, 0, 100)
    payload[3] = 8 if state.mode == 3 else 0
    payload[4] = state.direction if spec.uses_direction else 1
    payload[5:8] = bytes((state.red, state.green, state.blue))
    payload[9] = 1
    return bytes(payload)


def build_static_activation(brightness: int) -> bytes:
    payload = bytearray(16)
    payload[2] = _clamp(brightness, 0, 100)
    payload[9] = 1
    return bytes(payload)


def build_static_payload(zone: int, color: Iterable[int]) -> bytes:
    zone = int(zone)
    if zone < 1 or zone > 4:
        raise ValueError("Zone must be between 1 and 4")
    red, green, blue = (_clamp(component, 0, 255) for component in color)
    return bytes((1 << (zone - 1), red, green, blue))


class FacerController:
    def __init__(self, dynamic_device=DYNAMIC_DEVICE, static_device=STATIC_DEVICE, demo=False):
        self.dynamic_device = Path(dynamic_device)
        self.static_device = Path(static_device)
        self.demo = bool(demo)
        self.last_demo_payloads = []
        self._thread_lock = threading.Lock()
        self._software_frame = None
        runtime = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
        self.lock_path = runtime / "facer-studio-{}.lock".format(os.getuid())

    def status(self) -> dict:
        if self.demo:
            return {"available": True, "writable": True, "demo": True, "message": "Демо-режим"}
        dynamic_exists = self.dynamic_device.exists()
        static_exists = self.static_device.exists()
        writable = dynamic_exists and os.access(str(self.dynamic_device), os.W_OK)
        if not dynamic_exists:
            message = "Драйвер Facer не подключён"
        elif not writable:
            message = "Нет прав на управление"
        elif not static_exists:
            message = "Доступны только эффекты"
        else:
            message = "Клавиатура подключена"
        return {
            "available": dynamic_exists,
            "static_available": static_exists,
            "writable": writable,
            "demo": False,
            "message": message,
        }

    @contextmanager
    def _transaction(self):
        with self._thread_lock:
            if self.demo:
                yield
                return
            flags = os.O_RDWR | os.O_CREAT
            flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            lock_fd = None
            try:
                lock_fd = os.open(str(self.lock_path), flags, 0o600)
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
            except OSError as error:
                if lock_fd is not None:
                    os.close(lock_fd)
                raise DeviceWriteError("Не удалось заблокировать доступ к Facer: {}".format(error)) from error
            try:
                yield
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)

    def _write(self, path: Path, payload: bytes) -> None:
        if self.demo:
            self.last_demo_payloads.append((str(path), payload))
            return
        flags = os.O_WRONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(str(path), flags)
        except OSError as error:
            if error.errno == errno.ENOENT:
                raise DeviceMissingError(
                    "Устройство {} не найдено. Проверьте, что модуль Facer загружен.".format(path)
                ) from error
            if error.errno in (errno.EACCES, errno.EPERM):
                raise DevicePermissionError(
                    "Нет права записи в {}. Нужно правило udev для Facer.".format(path)
                ) from error
            raise DeviceWriteError("Не удалось открыть {}: {}".format(path, error)) from error
        try:
            if not stat.S_ISCHR(os.fstat(descriptor).st_mode):
                raise DeviceWriteError("{} не является символьным устройством.".format(path))
            written = os.write(descriptor, payload)
        except OSError as error:
            if error.errno in (errno.ENODEV, errno.ENXIO):
                raise DeviceMissingError("Устройство Facer отключилось во время записи.") from error
            if error.errno in (errno.EACCES, errno.EPERM):
                raise DevicePermissionError("Система запретила запись в {}.".format(path)) from error
            raise DeviceWriteError("Не удалось записать в {}: {}".format(path, error)) from error
        finally:
            os.close(descriptor)
        if written != len(payload):
            raise DeviceWriteError(
                "Драйвер принял только {} из {} байт.".format(written, len(payload))
            )

    def apply(self, state: LightingState) -> None:
        state = state.normalized()
        with self._transaction():
            # A normal hardware command invalidates the software-frame cache,
            # even if the following firmware call only succeeds partially.
            self._software_frame = None
            if state.mode == 0:
                for zone in state.zones:
                    try:
                        self._write(
                            self.static_device,
                            build_static_payload(zone, state.zone_colors[zone - 1]),
                        )
                    except FacerError as error:
                        raise DeviceWriteError(
                            "Статичный режим применён частично: ошибка на зоне {}. {}".format(zone, error)
                        ) from error
            activation = build_static_activation(state.brightness) if state.mode == 0 else build_dynamic_payload(state)
            self._write(self.dynamic_device, activation)

    def enter_software_mode(
        self, frame: SoftwareFrame, brightness: int
    ) -> Tuple[int, int, int, int]:
        """Write a complete four-zone frame and activate static firmware mode.

        Brightness is deliberately sent only by this entry operation. Later
        frames use the four-byte static-zone protocol and can change RGB only.
        """

        if not isinstance(frame, SoftwareFrame):
            frame = SoftwareFrame(tuple(frame))
        with self._transaction():
            self._software_frame = None
            for zone, color in enumerate(frame.zones, 1):
                try:
                    self._write(
                        self.static_device,
                        build_static_payload(zone, color.as_tuple()),
                    )
                except FacerError as error:
                    raise DeviceWriteError(
                        "Программный режим применён частично: ошибка на зоне {}. {}".format(
                            zone, error
                        )
                    ) from error
            self._write(self.dynamic_device, build_static_activation(brightness))
            self._software_frame = frame
        return (1, 2, 3, 4)

    def update_software_frame(self, frame: SoftwareFrame) -> Tuple[int, ...]:
        """Write only zones whose RGB differs from the last software frame."""

        if not isinstance(frame, SoftwareFrame):
            frame = SoftwareFrame(tuple(frame))
        with self._transaction():
            if self._software_frame is None:
                raise SoftwareModeInactiveError(
                    "Сначала активируйте программный режим полным кадром."
                )

            current = list(self._software_frame.zones)
            changed_zones = tuple(
                zone
                for zone, (old_color, new_color) in enumerate(
                    zip(current, frame.zones), 1
                )
                if old_color != new_color
            )
            for zone in changed_zones:
                color = frame.zones[zone - 1]
                try:
                    self._write(
                        self.static_device,
                        build_static_payload(zone, color.as_tuple()),
                    )
                except FacerError as error:
                    # Preserve knowledge of zones that were already written so
                    # a retry does not add avoidable WMI traffic.
                    self._software_frame = SoftwareFrame(tuple(current))
                    raise DeviceWriteError(
                        "Программный кадр применён частично: ошибка на зоне {}. {}".format(
                            zone, error
                        )
                    ) from error
                current[zone - 1] = color
            self._software_frame = frame
        return changed_zones

    def turn_off(self, state: LightingState) -> None:
        with self._transaction():
            self._software_frame = None
            payload = build_static_activation(0) if state.mode == 0 else build_dynamic_payload(state, brightness=0)
            self._write(self.dynamic_device, payload)
