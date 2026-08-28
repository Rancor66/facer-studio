"""Pure renderers for Facer Studio's software effects.

The functions in this module deliberately keep no timers or mutable state.  A
caller supplies elapsed monotonic time and receives a complete four-zone frame;
this makes animation restart, preview and hardware output use the exact same
deterministic renderer.
"""

from dataclasses import dataclass
import colorsys
import math
from typing import Callable, Dict, Iterable, Optional, Sequence, Tuple, Union

from .backend import RGBColor, SoftwareFrame


RGBValue = Union[RGBColor, Iterable[int]]
Palette = Tuple[RGBColor, ...]
ZoneColors = Tuple[RGBColor, RGBColor, RGBColor, RGBColor]


@dataclass(frozen=True)
class SoftwareEffectSpec:
    key: str
    name: str
    caption: str
    uses_palette: bool = False


SOFTWARE_EFFECTS: Tuple[SoftwareEffectSpec, ...] = (
    SoftwareEffectSpec("aurora", "Аврора", "Переливающийся градиент"),
    SoftwareEffectSpec("comet", "Комета", "Импульс с хвостом"),
    SoftwareEffectSpec("palette", "Палитра", "Переход между цветами", True),
    SoftwareEffectSpec("zone_breathing", "Дыхание по зонам", "Общая мягкая пульсация"),
    SoftwareEffectSpec("zone_shifting", "Перелив по зонам", "Сдвиг выбранных оттенков"),
    SoftwareEffectSpec("zone_impulse", "Импульс по зонам", "Пульс из центра"),
)
SOFTWARE_EFFECT_BY_KEY: Dict[str, SoftwareEffectSpec] = {
    effect.key: effect for effect in SOFTWARE_EFFECTS
}


def _elapsed(value: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(result):
        return 0.0
    return max(0.0, result)


def _speed(value: int) -> int:
    try:
        return max(0, min(9, int(value)))
    except (TypeError, ValueError):
        return 4


def _direction(value: int) -> float:
    try:
        return -1.0 if int(value) == 2 else 1.0
    except (TypeError, ValueError):
        return 1.0


def _rgb_from_hsv(hue: float, saturation: float, value: float) -> RGBColor:
    red, green, blue = colorsys.hsv_to_rgb(
        hue % 1.0,
        max(0.0, min(1.0, saturation)),
        max(0.0, min(1.0, value)),
    )
    return RGBColor(round(red * 255), round(green * 255), round(blue * 255))


def _companion_color(color: RGBColor) -> RGBColor:
    hue, saturation, value = colorsys.rgb_to_hsv(
        color.red / 255.0, color.green / 255.0, color.blue / 255.0
    )
    return _rgb_from_hsv(
        hue + 0.5,
        max(0.62, saturation),
        max(0.72, value),
    )


def normalize_palette(
    colors: Optional[Sequence[RGBValue]],
    base_color: RGBValue = (145, 55, 255),
) -> Palette:
    """Return a firmware-safe palette containing between two and eight colors.

    Empty and one-color selections are completed with a contrasting color, so
    even a partially configured profile remains animatable.  Extra colors are
    predictably ignored rather than making old profiles invalid.
    """

    base = RGBColor.from_value(base_color)
    normalized = tuple(RGBColor.from_value(color) for color in (colors or ()))[:8]
    if not normalized:
        normalized = (base,)
    if len(normalized) == 1:
        normalized += (_companion_color(normalized[0]),)
    return normalized


def normalize_zone_colors(
    colors: Optional[Sequence[RGBValue]],
    base_color: RGBValue = (145, 55, 255),
) -> ZoneColors:
    """Return exactly one safe base color for each physical keyboard zone.

    ``None`` and malformed/missing entries fall back to ``base_color``.  This
    deliberately differs from :func:`normalize_palette`: a palette is a cyclic
    list whose length has meaning, while zone colors are four fixed positions.
    """

    base = RGBColor.from_value(base_color)
    fallback: ZoneColors = (base, base, base, base)
    if colors is None or isinstance(colors, (str, bytes)):
        return fallback
    try:
        supplied = tuple(colors)[:4]
    except TypeError:
        return fallback

    normalized = []
    for zone in range(4):
        if zone >= len(supplied):
            normalized.append(base)
            continue
        try:
            normalized.append(RGBColor.from_value(supplied[zone]))
        except (TypeError, ValueError, OverflowError):
            normalized.append(base)
    return tuple(normalized)  # type: ignore[return-value]


def _smooth_mix(first: RGBColor, second: RGBColor, amount: float) -> RGBColor:
    amount = max(0.0, min(1.0, float(amount)))
    # Cosine interpolation has zero slope at each selected color.  Consequently
    # the final-to-first wrap is as smooth as all the internal transitions.
    blend = 0.5 - 0.5 * math.cos(math.pi * amount)
    return RGBColor(
        round(first.red + (second.red - first.red) * blend),
        round(first.green + (second.green - first.green) * blend),
        round(first.blue + (second.blue - first.blue) * blend),
    )


def palette_color(colors: Sequence[RGBValue], position: float) -> RGBColor:
    """Sample a cyclic palette; integer positions are exact selected colors."""

    palette = normalize_palette(colors)
    try:
        numeric_position = float(position)
    except (TypeError, ValueError):
        numeric_position = 0.0
    if not math.isfinite(numeric_position):
        numeric_position = 0.0
    wrapped = numeric_position % len(palette)
    index = int(math.floor(wrapped))
    fraction = wrapped - index
    return _smooth_mix(
        palette[index], palette[(index + 1) % len(palette)], fraction
    )


def render_aurora(
    elapsed: float,
    base_color: RGBValue = (145, 55, 255),
    speed: int = 4,
    direction: int = 1,
    zone_colors: Optional[Sequence[RGBValue]] = None,
) -> SoftwareFrame:
    """Render a flowing gradient, optionally anchored to four zone colors.

    With no ``zone_colors`` this retains the original single-color hue-flow
    renderer.  Four supplied colors instead define the hue of each physical
    zone while a travelling brightness gradient supplies the Aurora motion.
    """

    base = RGBColor.from_value(base_color)
    travel = _elapsed(elapsed) * (0.070 + 0.026 * _speed(speed)) * _direction(direction)
    if zone_colors is not None:
        colors = []
        for zone, zone_base in enumerate(normalize_zone_colors(zone_colors, base)):
            phase = math.tau * (zone / 4.0 - travel)
            wave = 0.5 + 0.5 * math.sin(phase + 1.05)
            shimmer = 0.5 + 0.5 * math.sin(2.0 * phase + 0.7)
            level = min(1.0, 0.48 + 0.43 * wave + 0.09 * shimmer)
            colors.append(
                RGBColor(
                    round(zone_base.red * level),
                    round(zone_base.green * level),
                    round(zone_base.blue * level),
                )
            )
        return SoftwareFrame(tuple(colors))

    base_hue, base_saturation, base_value = colorsys.rgb_to_hsv(
        base.red / 255.0, base.green / 255.0, base.blue / 255.0
    )
    # One slow travelling wave provides the main gradient; a second harmonic
    # keeps four physical zones from merely looking like a rotated color list.
    colors = []
    for zone in range(4):
        phase = math.tau * (zone / 4.0 - travel)
        hue = base_hue + 0.19 * math.sin(phase) + 0.045 * math.sin(2.0 * phase + 0.7)
        saturation = max(0.58, base_saturation) * (
            0.88 + 0.12 * (0.5 + 0.5 * math.cos(phase + 0.35))
        )
        value_wave = 0.5 + 0.5 * math.sin(phase + 1.05)
        value = max(0.52, base_value * 0.70) + 0.34 * value_wave
        colors.append(_rgb_from_hsv(hue, saturation, min(1.0, value)))
    return SoftwareFrame(tuple(colors))


def _comet_position(elapsed: float, velocity: float, direction: int) -> float:
    maximum = 3.0
    leg = (_elapsed(elapsed) * velocity) % (maximum * 2.0)
    position = leg if leg <= maximum else maximum * 2.0 - leg
    if _direction(direction) < 0.0:
        position = maximum - position
    return position


def _comet_color(base: RGBColor, intensity: float, head: float) -> RGBColor:
    intensity = max(0.0, min(1.0, intensity))
    if intensity < 0.002:
        return RGBColor(0, 0, 0)
    # Raising dim parts makes the tail visible on real keycaps.  Only the head
    # is mixed toward white, so the chosen color remains clear along the tail.
    visible = intensity ** 0.72
    white_mix = 0.24 * max(0.0, min(1.0, head))
    return RGBColor(
        round(base.red * visible * (1.0 - white_mix) + 255.0 * visible * white_mix),
        round(base.green * visible * (1.0 - white_mix) + 255.0 * visible * white_mix),
        round(base.blue * visible * (1.0 - white_mix) + 255.0 * visible * white_mix),
    )


def render_comet(
    elapsed: float,
    base_color: RGBValue = (145, 55, 255),
    speed: int = 4,
    direction: int = 1,
    zone_colors: Optional[Sequence[RGBValue]] = None,
) -> SoftwareFrame:
    """Render a bright impulse bouncing between the edge zones with a tail.

    The tail is reconstructed from earlier positions on the reflected path.
    This is still a pure function, while avoiding an abrupt tail flip when the
    comet touches an edge and changes direction.
    """

    base = RGBColor.from_value(base_color)
    zone_bases = normalize_zone_colors(zone_colors, base)
    now = _elapsed(elapsed)
    velocity = 0.48 + 0.17 * _speed(speed)  # physical zones per second
    position = _comet_position(now, velocity, direction)
    head_width = 0.30
    tail_distance = 2.8
    tail_duration = tail_distance / velocity
    history_duration = min(now, tail_duration)
    samples = 32
    intensities = [0.0, 0.0, 0.0, 0.0]
    heads = []
    for zone in range(4):
        head = math.exp(-0.5 * ((zone - position) / head_width) ** 2)
        heads.append(head)
        intensities[zone] = head

    if history_duration > 0.0:
        decay_time = 1.35 / velocity
        for sample in range(1, samples + 1):
            age = history_duration * sample / samples
            old_position = _comet_position(now - age, velocity, direction)
            strength = math.exp(-age / decay_time)
            for zone in range(4):
                footprint = math.exp(
                    -0.5 * ((zone - old_position) / head_width) ** 2
                )
                intensities[zone] = max(
                    intensities[zone], strength * footprint
                )

    return SoftwareFrame(
        tuple(
            _comet_color(zone_base, intensity, head)
            for zone_base, intensity, head in zip(zone_bases, intensities, heads)
        )
    )


def render_palette(
    elapsed: float,
    palette: Optional[Sequence[RGBValue]] = None,
    base_color: RGBValue = (145, 55, 255),
    speed: int = 4,
    direction: int = 1,
) -> SoftwareFrame:
    """Render smooth cyclic transitions through two to eight selected colors."""

    colors = normalize_palette(palette, base_color)
    phase = (
        _elapsed(elapsed)
        * (0.10 + 0.045 * _speed(speed))
        * _direction(direction)
    )
    spacing = len(colors) / 4.0
    return SoftwareFrame(
        tuple(palette_color(colors, phase + zone * spacing) for zone in range(4))
    )


def _scale_color(color: RGBColor, level: float) -> RGBColor:
    """Scale one selected RGB color without changing its hue."""

    level = max(0.0, min(1.0, float(level)))
    return RGBColor(
        round(color.red * level),
        round(color.green * level),
        round(color.blue * level),
    )


def render_zone_breathing(
    elapsed: float,
    base_color: RGBValue = (145, 55, 255),
    speed: int = 4,
    direction: int = 1,
    zone_colors: Optional[Sequence[RGBValue]] = None,
) -> SoftwareFrame:
    """Fade all four selected zone colors in and out on one smooth clock."""

    # Breathing has no spatial direction, but accepts the common renderer
    # signature so it can be dispatched exactly like the other effects.
    del direction
    base = RGBColor.from_value(base_color)
    colors = normalize_zone_colors(zone_colors, base)
    cycle_rate = 0.10 + 0.035 * _speed(speed)
    phase = math.tau * _elapsed(elapsed) * cycle_rate
    inhale = 0.5 - 0.5 * math.cos(phase)
    level = 0.16 + 0.84 * inhale
    return SoftwareFrame(tuple(_scale_color(color, level) for color in colors))


def render_zone_shifting(
    elapsed: float,
    base_color: RGBValue = (145, 55, 255),
    speed: int = 4,
    direction: int = 1,
    zone_colors: Optional[Sequence[RGBValue]] = None,
) -> SoftwareFrame:
    """Shift every selected zone hue smoothly in the requested direction."""

    base = RGBColor.from_value(base_color)
    colors = normalize_zone_colors(zone_colors, base)
    hue_shift = (
        _elapsed(elapsed)
        * (0.035 + 0.016 * _speed(speed))
        * _direction(direction)
    )
    shifted = []
    for color in colors:
        hue, saturation, value = colorsys.rgb_to_hsv(
            color.red / 255.0,
            color.green / 255.0,
            color.blue / 255.0,
        )
        shifted.append(_rgb_from_hsv(hue + hue_shift, saturation, value))
    return SoftwareFrame(tuple(shifted))


def render_zone_impulse(
    elapsed: float,
    base_color: RGBValue = (145, 55, 255),
    speed: int = 4,
    direction: int = 1,
    zone_colors: Optional[Sequence[RGBValue]] = None,
) -> SoftwareFrame:
    """Send a soft pulse from the two centre zones toward both edges."""

    # The firmware's centre impulse has no left/right direction.  Keeping this
    # argument makes the software analogue conform to the shared effect API.
    del direction
    base = RGBColor.from_value(base_color)
    colors = normalize_zone_colors(zone_colors, base)
    cycle_rate = 0.18 + 0.045 * _speed(speed)
    progress = (_elapsed(elapsed) * cycle_rate) % 1.0
    levels = []
    for zone in range(4):
        # Zones 2/3 are the centre pair.  The same crest reaches zones 1/4 a
        # little later, making the motion symmetrical and visibly outward.
        distance_from_centre = abs(zone - 1.5)
        delay = 0.24 * (distance_from_centre - 0.5)
        local_phase = (progress - delay) % 1.0
        crest = (0.5 + 0.5 * math.cos(math.tau * local_phase)) ** 4
        levels.append(0.10 + 0.90 * crest)
    return SoftwareFrame(
        tuple(_scale_color(color, level) for color, level in zip(colors, levels))
    )


Renderer = Callable[..., SoftwareFrame]
EFFECT_RENDERERS: Dict[str, Renderer] = {
    "aurora": render_aurora,
    "comet": render_comet,
    "palette": render_palette,
    "zone_breathing": render_zone_breathing,
    "zone_shifting": render_zone_shifting,
    "zone_impulse": render_zone_impulse,
}


def render_effect(
    effect: str,
    elapsed: float,
    base_color: RGBValue = (145, 55, 255),
    speed: int = 4,
    direction: int = 1,
    palette: Optional[Sequence[RGBValue]] = None,
    zone_colors: Optional[Sequence[RGBValue]] = None,
) -> SoftwareFrame:
    """Render one named effect using normalized, state-like parameters."""

    key = str(effect).strip().lower()
    if key not in EFFECT_RENDERERS:
        raise ValueError("Unknown software effect: {}".format(effect))
    if key == "palette":
        return render_palette(
            elapsed,
            palette=palette if palette is not None else zone_colors,
            base_color=base_color,
            speed=speed,
            direction=direction,
        )
    return EFFECT_RENDERERS[key](
        elapsed,
        base_color=base_color,
        speed=speed,
        direction=direction,
        zone_colors=zone_colors,
    )
