"""Main Qt window for Facer Studio."""

from dataclasses import dataclass
from functools import partial
from pathlib import Path
import threading
import time

from PyQt6.QtCore import QPropertyAnimation, QThread, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QIcon, QIntValidator
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPushButton,
    QScrollArea,
    QSlider,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

from .backend import (
    DEFAULT_PALETTE,
    FacerController,
    FacerError,
    LightingState,
    MODE_BY_INDEX,
    MODES,
)
from .effects import render_effect
from .i18n import (
    BUILTIN_PROFILE_TRANSLATION_KEYS,
    DEVICE_STATUS_TRANSLATION_KEYS,
    HARDWARE_MODE_TRANSLATION_KEYS,
    SOFTWARE_MODE_TRANSLATION_KEYS,
    normalize_language,
    tr,
    translate_runtime_message,
)
from .storage import BUILTIN_PROFILES, ProfileStore
from .widgets import ColorWheel, KeyboardPreview


ACCENT = "#a855f7"
APP_DIR = Path(__file__).resolve().parent.parent
PROFILE_CANONICAL_ROLE = Qt.ItemDataRole.UserRole.value + 1
STARTUP_RESTORE_INITIAL_DELAY_MS = 700
STARTUP_RESTORE_RETRY_MS = 4000
STATUS_TOAST_DURATION_MS = 5000

@dataclass(frozen=True)
class SoftwareModeSpec:
    button_id: int
    effect: str
    name: str
    caption: str
    note: str
    uses_direction: bool = False


SOFTWARE_MODES = (
    SoftwareModeSpec(
        101,
        "aurora",
        "Аврора",
        "Живой градиент",
        "✦ Градиент течёт через четыре выбранных цвета.",
        True,
    ),
    SoftwareModeSpec(
        102,
        "comet",
        "Комета",
        "Импульс с хвостом",
        "☄ Ядро с хвостом проходит зоны в выбранных цветах.",
    ),
    SoftwareModeSpec(
        103,
        "palette",
        "Палитра",
        "Свои цвета",
        "◈ Зоны плавно переходят между четырьмя цветами.",
    ),
)
SOFTWARE_BY_ID = {mode.button_id: mode for mode in SOFTWARE_MODES}
SOFTWARE_BY_EFFECT = {mode.effect: mode for mode in SOFTWARE_MODES}
ZONE_COLOR_MODES = frozenset((0, 1, 4, 5))
ZONE_COLOR_EFFECTS = frozenset(("aurora", "comet", "palette"))
ZONE_MODE_EFFECTS = {
    1: "zone_breathing",
    4: "zone_shifting",
    5: "zone_impulse",
}


STYLE = """
QWidget {
    color: #eef0f8;
    font-family: "Noto Sans", "DejaVu Sans", sans-serif;
    font-size: 13px;
}
QMainWindow { background: #08090d; }
QWidget#root { background: #08090d; }
QFrame#card, QWidget#card {
    background: #12141d;
    border: 1px solid #252838;
    border-radius: 16px;
}
QLabel#brand { font-size: 25px; font-weight: 700; color: #ffffff; }
QLabel#subtitle, QLabel#muted { color: #85899c; }
QLabel#section { color: #a8abba; font-size: 11px; font-weight: 700; }
QLabel#value { color: #ffffff; font-size: 12px; font-weight: 700; }
QLabel#statusOnline {
    color: #8cf5bc; background: #10271d; border: 1px solid #1f6d48;
    border-radius: 12px; padding: 5px 11px;
}
QLabel#statusOffline {
    color: #ffb2bc; background: #2a141a; border: 1px solid #73313c;
    border-radius: 12px; padding: 5px 11px;
}
QLabel#effectNote {
    color: #d9bcff; background: #21162d; border: 1px solid #643790;
    border-radius: 9px; padding: 7px 9px;
}
QPushButton {
    min-height: 34px; padding: 4px 12px; background: #1a1d28;
    border: 1px solid #303446; border-radius: 9px; color: #e6e8f1;
}
QPushButton:hover { background: #222636; border-color: #555b74; }
QPushButton:pressed { background: #171925; }
QPushButton#modeButton {
    text-align: left; min-height: 43px; padding: 5px 12px; border-radius: 11px;
    background: transparent; border: 1px solid transparent; color: #b4b7c6;
}
QPushButton#modeButton:hover { background: #181a25; color: #ffffff; }
QPushButton#modeButton:checked {
    background: #241832; border-color: #7b3fb2; color: #ffffff;
}
QPushButton#primary {
    min-height: 42px; background: #9345dc; border: 1px solid #bb72ff;
    color: white; font-weight: 700; border-radius: 11px;
}
QPushButton#primary:hover { background: #a855f7; }
QPushButton#danger { color: #ffabb7; }
QPushButton#segment:checked { background: #30203f; border-color: #9b54d4; color: white; }
QPushButton#swatch { min-width: 25px; max-width: 25px; min-height: 25px; max-height: 25px; border-radius: 13px; }
QPushButton#paletteSwatch {
    min-width: 42px; max-width: 42px; min-height: 30px; max-height: 30px;
    padding: 0; border: 2px solid #363a4b; border-radius: 8px;
}
QPushButton#paletteSwatch:checked { border: 3px solid #ffffff; }
QPushButton#zoneCopy {
    min-height: 24px; max-height: 24px; padding: 0 8px;
    color: #c8cbd8; background: #181b25; border-radius: 7px;
}
QPushButton#languageButton {
    min-width: 46px; max-width: 46px; min-height: 28px; max-height: 28px;
    padding: 0; color: #d9bcff; background: #21162d;
    border: 1px solid #643790; border-radius: 9px; font-weight: 700;
}
QPushButton#languageButton:hover { background: #30203f; border-color: #9b54d4; }
QSlider::groove:horizontal { height: 5px; background: #292c3a; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #a855f7; border-radius: 2px; }
QSlider::handle:horizontal {
    background: #ffffff; border: 3px solid #a855f7; width: 15px;
    margin: -7px 0; border-radius: 10px;
}
QCheckBox { spacing: 7px; color: #c5c8d4; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #4a4e61; border-radius: 5px; background: #151721; }
QCheckBox::indicator:checked { background: #a855f7; border-color: #c083fa; }
QLineEdit {
    min-height: 32px; padding: 0 9px; background: #0e1017;
    border: 1px solid #303446; border-radius: 8px; selection-background-color: #7940ad;
}
QLineEdit:focus { border-color: #a855f7; }
QListWidget {
    background: #0e1017; border: 1px solid #272a38; border-radius: 9px;
    outline: none; padding: 4px;
}
QListWidget::item { padding: 7px 8px; border-radius: 6px; color: #c3c6d3; }
QListWidget::item:selected { background: #312042; color: #ffffff; }
QToolTip { background: #202330; color: white; border: 1px solid #45495b; padding: 5px; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical {
    background: transparent; width: 7px; margin: 2px 0;
}
QScrollBar::handle:vertical {
    background: #3d4051; min-height: 28px; border-radius: 3px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def _card(layout, object_name="card"):
    frame = QFrame()
    frame.setObjectName(object_name)
    frame.setLayout(layout)
    return frame


class DeviceWorker(QThread):
    """The sole device writer, with control commands taking priority over frames.

    Software frames carry a generation number.  This prevents a delayed frame
    or error from an old effect from cancelling a newer effect after a quick
    mode switch.
    """

    operationFinished = pyqtSignal(bool, str, bool, str, int)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._condition = threading.Condition()
        self._control_pending = None
        self._frame_pending = None
        self._software_generation = 0
        self._software_ready = False
        self._stopping = False

    def submit(self, action, state, show_dialog=False, generation=0):
        with self._condition:
            if self._stopping:
                return False
            if action in ("apply", "off"):
                self._software_generation = 0
                self._software_ready = False
                self._frame_pending = None
            elif action == "enter_software":
                generation = int(generation)
                if generation <= 0:
                    raise ValueError("Software session generation must be positive")
                self._software_generation = generation
                self._software_ready = False
                self._frame_pending = None
            if (
                self._control_pending is not None
                and action == "apply"
                and self._control_pending[0] == "apply"
            ):
                show_dialog = show_dialog or self._control_pending[2]
            self._control_pending = (action, state, show_dialog, int(generation))
            self._condition.notify()
            return True

    def submit_frame(self, frame, generation):
        with self._condition:
            generation = int(generation)
            if generation != self._software_generation or self._stopping:
                return False
            self._frame_pending = (generation, frame)
            self._condition.notify()
            return True

    def cancel_software(self, generation=None):
        with self._condition:
            if (
                generation is not None
                and int(generation) != self._software_generation
            ):
                return False
            cancelled_generation = self._software_generation
            self._software_generation = 0
            self._software_ready = False
            self._frame_pending = None
            if (
                self._control_pending is not None
                and self._control_pending[0] == "enter_software"
                and (
                    generation is None
                    or self._control_pending[3] == int(generation)
                )
            ):
                self._control_pending = None
            return bool(cancelled_generation)

    def stop(self):
        with self._condition:
            self._stopping = True
            self._software_generation = 0
            self._software_ready = False
            self._control_pending = None
            self._frame_pending = None
            self._condition.notify()

    def run(self):
        while True:
            with self._condition:
                while (
                    self._control_pending is None
                    and self._frame_pending is None
                    and not self._stopping
                ):
                    self._condition.wait()
                if self._stopping:
                    return
                if self._control_pending is not None:
                    action, state, show_dialog, generation = self._control_pending
                    self._control_pending = None
                else:
                    generation, state = self._frame_pending
                    action, show_dialog = "frame", False
                    self._frame_pending = None
                    if (
                        generation != self._software_generation
                        or not self._software_ready
                    ):
                        continue
            try:
                if action == "off":
                    self.controller.turn_off(state)
                elif action == "enter_software":
                    frame, brightness = state
                    self.controller.enter_software_mode(frame, brightness)
                elif action == "frame":
                    self.controller.update_software_frame(state)
                else:
                    self.controller.apply(state)
            except FacerError as error:
                if action in ("frame", "enter_software"):
                    self.cancel_software(generation)
                self.operationFinished.emit(
                    False, str(error), show_dialog, action, generation
                )
            except Exception as error:
                if action in ("frame", "enter_software"):
                    self.cancel_software(generation)
                self.operationFinished.emit(
                    False,
                    "Неожиданная ошибка: {}".format(error),
                    show_dialog,
                    action,
                    generation,
                )
            else:
                if action == "enter_software":
                    with self._condition:
                        if generation == self._software_generation:
                            self._software_ready = True
                self.operationFinished.emit(
                    True, "", show_dialog, action, generation
                )


class SliderRow(QWidget):
    changed = None

    def __init__(
        self,
        title,
        minimum,
        maximum,
        value,
        suffix="",
        parent=None,
        page_step=None,
    ):
        super().__init__(parent)
        self.suffix = suffix
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        heading = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setObjectName("muted")
        self.value_label = QLabel()
        self.value_label.setObjectName("value")
        heading.addWidget(self.title_label)
        heading.addStretch()
        heading.addWidget(self.value_label)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(minimum, maximum)
        if page_step is not None:
            self.slider.setSingleStep(1)
            self.slider.setPageStep(page_step)
        self.slider.setValue(value)
        self.slider.valueChanged.connect(self._update_value)
        layout.addLayout(heading)
        layout.addWidget(self.slider)
        self._update_value(value)
        self.changed = self.slider.valueChanged

    def _update_value(self, value):
        self.value_label.setText("{}{}".format(value, self.suffix))

    def value(self):
        return self.slider.value()

    def setValue(self, value):
        self.slider.setValue(value)

    def setTitle(self, title):
        self.title_label.setText(title)


class FacerWindow(QMainWindow):
    def __init__(self, controller=None, store=None, parent=None):
        super().__init__(parent)
        self.controller = controller or FacerController()
        self.store = store or ProfileStore()
        self.language = normalize_language(getattr(self.store, "language", "ru"))
        self._loading = True
        self._last_error = ""
        self._status_translation = None
        self._status_toast_active = False
        self._startup_restore_pending = False
        self._startup_restore_in_flight = False
        self._startup_restore_completed = False
        self._startup_restore_internal = False
        self._startup_restore_state = None
        self._startup_restore_expected_action = ""
        self._worker_stopped = False
        self._quitting = False
        self._tray_notice_shown = False
        self._software_started = False
        self._software_generation_counter = 0
        self._active_software_generation = 0
        self._active_visual_state = None
        self._active_visual_effect = ""
        self._visual_started_at = 0.0
        self._visual_show_dialog = False
        self.zone_colors = [(145, 55, 255)] * 4
        self.palette_colors = list(DEFAULT_PALETTE[:4])
        self.palette_active_index = 0
        self.setWindowTitle("Facer Studio")
        self.setMinimumSize(1060, 700)
        self.resize(1180, 780)
        icon = APP_DIR / "resources" / "facer-studio.svg"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.setStyleSheet(STYLE)
        self._build_ui()

        self.device_worker = DeviceWorker(self.controller, self)
        self.device_worker.operationFinished.connect(self._operation_finished)
        self.device_worker.start()

        self.apply_timer = QTimer(self)
        self.apply_timer.setSingleShot(True)
        self.apply_timer.setInterval(180)
        self.apply_timer.timeout.connect(partial(self.apply_state, False))

        self.startup_restore_timer = QTimer(self)
        self.startup_restore_timer.setSingleShot(True)
        self.startup_restore_timer.timeout.connect(
            self._attempt_startup_restore
        )

        self.effect_timer = QTimer(self)
        self.effect_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.effect_timer.setInterval(200)
        self.effect_timer.timeout.connect(self._render_visual_frame)

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.refresh_status)
        self.status_timer.start(2500)

        self.load_state(self.store.last_state)
        self.live_checkbox.setChecked(self.store.live_apply)
        self._loading = False
        self._controls_changed()
        self.refresh_profiles()
        self.refresh_status()
        self._setup_tray()
        self._retranslate_ui()

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(24, 20, 24, 22)
        outer.setSpacing(16)

        header = QHBoxLayout()
        self.brand_label = QLabel("FACER  <span style='color:#a855f7'>STUDIO</span>")
        self.brand_label.setObjectName("brand")
        self.subtitle_label = QLabel(root)
        self.subtitle_label.setObjectName("subtitle")
        self.subtitle_label.hide()
        header.addWidget(self.brand_label)
        header.addStretch()
        self.status_label = QLabel()
        self.status_opacity_effect = QGraphicsOpacityEffect(self.status_label)
        self.status_opacity_effect.setOpacity(1.0)
        self.status_label.setGraphicsEffect(self.status_opacity_effect)
        self.status_toast_animation = QPropertyAnimation(
            self.status_opacity_effect,
            b"opacity",
            self,
        )
        self.status_toast_animation.setDuration(STATUS_TOAST_DURATION_MS)
        self.status_toast_animation.setStartValue(0.0)
        self.status_toast_animation.setKeyValueAt(0.04, 1.0)
        self.status_toast_animation.setKeyValueAt(0.88, 1.0)
        self.status_toast_animation.setEndValue(0.0)
        self.status_toast_animation.finished.connect(
            self._finish_status_toast
        )
        header.addWidget(self.status_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.language_button = QPushButton()
        self.language_button.setObjectName("languageButton")
        self.language_button.clicked.connect(self._toggle_language)
        header.addWidget(self.language_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        outer.addLayout(header)

        content = QHBoxLayout()
        content.setSpacing(14)
        content.addWidget(self._build_modes(), 0)
        content.addLayout(self._build_center(), 1)
        content.addWidget(self._build_controls(), 0)
        outer.addLayout(content, 1)
        self.setCentralWidget(root)

    def _build_modes(self):
        mode_container = QWidget()
        layout = QVBoxLayout(mode_container)
        layout.setContentsMargins(13, 16, 13, 16)
        layout.setSpacing(5)
        self.modes_title = QLabel()
        self.modes_title.setObjectName("section")
        layout.addWidget(self.modes_title)
        layout.addSpacing(5)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_buttons = {}
        for mode in MODES:
            button = QPushButton("{}\n  {}".format(mode.name, mode.caption))
            button.setObjectName("modeButton")
            button.setCheckable(True)
            button.setProperty("mode", mode.index)
            button.clicked.connect(partial(self._select_mode, mode.index))
            self.mode_group.addButton(button, mode.index)
            self.mode_buttons[mode.index] = button
            layout.addWidget(button)
        layout.addSpacing(9)
        self.software_modes_title = QLabel()
        self.software_modes_title.setObjectName("section")
        layout.addWidget(self.software_modes_title)
        for mode in SOFTWARE_MODES:
            button = QPushButton("{}\n  {}".format(mode.name, mode.caption))
            button.setObjectName("modeButton")
            button.setCheckable(True)
            button.setProperty("mode", mode.button_id)
            button.setToolTip(mode.note)
            button.clicked.connect(partial(self._select_mode, mode.button_id))
            self.mode_group.addButton(button, mode.button_id)
            self.mode_buttons[mode.button_id] = button
            layout.addWidget(button)
        layout.addStretch()
        self.mode_footer = QLabel(mode_container)
        self.mode_footer.setObjectName("muted")
        self.mode_footer.hide()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(mode_container)
        self.mode_scroll = scroll
        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.addWidget(scroll)
        frame = _card(card_layout)
        frame.setFixedWidth(205)
        return frame

    def _build_center(self):
        column = QVBoxLayout()
        column.setSpacing(14)

        preview_layout = QVBoxLayout()
        preview_layout.setContentsMargins(16, 14, 16, 12)
        preview_header = QHBoxLayout()
        self.preview_title = QLabel()
        self.preview_title.setObjectName("section")
        self.mode_caption = QLabel()
        self.mode_caption.setObjectName("muted")
        preview_header.addWidget(self.preview_title)
        preview_header.addStretch()
        preview_header.addWidget(self.mode_caption)
        preview_layout.addLayout(preview_header)
        self.preview = KeyboardPreview()
        preview_layout.addWidget(self.preview, 1)
        column.addWidget(_card(preview_layout), 1)

        color_layout = QHBoxLayout()
        color_layout.setContentsMargins(18, 15, 18, 15)
        color_layout.setSpacing(15)
        wheel_column = QVBoxLayout()
        self.color_title = QLabel()
        self.color_title.setObjectName("section")
        wheel_column.addWidget(self.color_title)
        self.color_wheel = ColorWheel()
        self.color_wheel.colorChanged.connect(self._color_changed)
        wheel_column.addWidget(self.color_wheel, 1)
        color_layout.addLayout(wheel_column, 1)

        color_details = QVBoxLayout()
        color_details.setSpacing(10)
        color_details.addStretch()
        self.color_chip = QLabel()
        self.color_chip.setFixedHeight(54)
        color_details.addWidget(self.color_chip)
        hex_line = QHBoxLayout()
        hex_label = QLabel("HEX")
        hex_label.setObjectName("muted")
        self.hex_input = QLineEdit("#9137FF")
        self.hex_input.setMaxLength(7)
        self.hex_input.editingFinished.connect(self._hex_edited)
        hex_line.addWidget(hex_label)
        hex_line.addWidget(self.hex_input)
        color_details.addLayout(hex_line)
        rgb_line = QHBoxLayout()
        self.rgb_inputs = []
        for caption in ("R", "G", "B"):
            rgb_line.addWidget(QLabel(caption))
            editor = QLineEdit()
            editor.setFixedWidth(50)
            editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
            editor.setValidator(QIntValidator(0, 255, editor))
            editor.editingFinished.connect(self._rgb_edited)
            self.rgb_inputs.append(editor)
            rgb_line.addWidget(editor)
        color_details.addLayout(rgb_line)
        swatches = QHBoxLayout()
        for value in ("#9137ff", "#ff2d8d", "#22d3ee", "#24e596", "#ff8a34"):
            button = QPushButton()
            button.setObjectName("swatch")
            button.setStyleSheet("QPushButton#swatch { background: %s; border: 2px solid rgba(255,255,255,35); }" % value)
            button.setToolTip(value.upper())
            button.clicked.connect(partial(self._set_color, QColor(value)))
            swatches.addWidget(button)
        color_details.addLayout(swatches)
        color_details.addStretch()
        color_layout.addLayout(color_details)
        self.color_card = _card(color_layout)
        self.color_card_opacity_effect = QGraphicsOpacityEffect(self.color_card)
        self.color_card_opacity_effect.setOpacity(1.0)
        self.color_card.setGraphicsEffect(self.color_card_opacity_effect)
        column.addWidget(self.color_card, 1)
        return column

    def _build_controls(self):
        controls_container = QWidget()
        controls_container.setObjectName("controlsContainer")
        layout = QVBoxLayout(controls_container)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(14, 13, 14, 13)
        # Every settings group occupies a permanent vertical slot.  Hiding an
        # option therefore only empties its slot instead of making all rows
        # below it jump.  The fixed minimum is a little taller than the
        # 1060x700 viewport, where the existing outer QScrollArea takes over;
        # at the normal 1180x780 size it fits without overlapping anything.
        layout.setSpacing(6)
        self.settings_title = QLabel()
        self.settings_title.setObjectName("section")
        self.settings_title.setFixedHeight(16)
        layout.addWidget(self.settings_title)

        self.brightness = SliderRow("Яркость", 0, 100, 80, "%")
        self.speed = SliderRow(
            "Скорость",
            0,
            9,
            4,
            page_step=1,
        )
        self.brightness.setFixedHeight(37)
        self.speed.setFixedHeight(37)
        self.brightness.changed.connect(self._controls_changed)
        self.speed.changed.connect(self._controls_changed)
        layout.addWidget(self.brightness)
        self.speed_slot = self._fixed_control_slot(self.speed, 37)
        layout.addWidget(self.speed_slot)

        self.direction_box = QWidget()
        direction_layout = QVBoxLayout(self.direction_box)
        direction_layout.setContentsMargins(0, 0, 0, 0)
        direction_layout.setSpacing(6)
        self.direction_label = QLabel(objectName="muted")
        direction_layout.addWidget(self.direction_label)
        direction_buttons = QHBoxLayout()
        self.direction_group = QButtonGroup(self)
        self.direction_group.setExclusive(True)
        self.direction_buttons = {}
        for value, text in ((1, "← Влево"), (2, "Вправо →")):
            button = QPushButton(text)
            button.setObjectName("segment")
            button.setCheckable(True)
            button.clicked.connect(self._controls_changed)
            self.direction_group.addButton(button, value)
            self.direction_buttons[value] = button
            direction_buttons.addWidget(button)
        direction_layout.addLayout(direction_buttons)
        self.zones_box = QWidget()
        zones_layout = QVBoxLayout(self.zones_box)
        zones_layout.setContentsMargins(0, 0, 0, 0)
        zones_layout.setSpacing(6)
        self.zones_label = QLabel(objectName="muted")
        zones_layout.addWidget(self.zones_label)
        zones_line = QHBoxLayout()
        self.zone_checks = []
        for zone in range(1, 5):
            check = QCheckBox(str(zone))
            check.stateChanged.connect(self._zones_changed)
            self.zone_checks.append(check)
            zones_line.addWidget(check)
        zones_line.addStretch()
        zones_layout.addLayout(zones_line)
        self.mode_options_slot = QWidget()
        self.mode_options_slot.setObjectName("modeOptionsSlot")
        self.mode_options_slot.setFixedHeight(66)
        mode_options_layout = QVBoxLayout(self.mode_options_slot)
        mode_options_layout.setContentsMargins(0, 0, 0, 0)
        mode_options_layout.setSpacing(0)
        mode_options_layout.addWidget(self.direction_box)
        mode_options_layout.addWidget(self.zones_box)
        layout.addWidget(self.mode_options_slot)

        self.palette_box = QWidget()
        palette_layout = QVBoxLayout(self.palette_box)
        palette_layout.setContentsMargins(0, 0, 0, 0)
        palette_layout.setSpacing(6)
        self.palette_label = QLabel("Цвета зон", objectName="muted")
        palette_layout.addWidget(self.palette_label)
        palette_line = QHBoxLayout()
        palette_line.setSpacing(7)
        self.palette_group = QButtonGroup(self)
        self.palette_group.setExclusive(True)
        self.palette_buttons = []
        for index in range(4):
            button = QPushButton()
            button.setObjectName("paletteSwatch")
            button.setCheckable(True)
            button.setToolTip("Цвет {} · выберите и настройте кругом".format(index + 1))
            button.clicked.connect(partial(self._select_palette_slot, index))
            self.palette_group.addButton(button, index)
            self.palette_buttons.append(button)
            palette_line.addWidget(button)
        palette_line.addStretch()
        self.palette_buttons[0].setChecked(True)
        palette_layout.addLayout(palette_line)
        palette_hint_line = QHBoxLayout()
        palette_hint_line.setSpacing(6)
        self.palette_hint = QLabel(
            "Слоты соответствуют физическим зонам слева направо"
        )
        self.palette_hint.setObjectName("muted")
        self.palette_hint.setWordWrap(True)
        palette_hint_line.addWidget(self.palette_hint, 1)
        self.copy_zone_color_button = QPushButton("Цвет → всем")
        self.copy_zone_color_button.setObjectName("zoneCopy")
        self.copy_zone_color_button.setToolTip(
            "Скопировать цвет активной зоны во все четыре зоны"
        )
        self.copy_zone_color_button.clicked.connect(self._copy_color_to_all_zones)
        palette_hint_line.addWidget(self.copy_zone_color_button)
        palette_layout.addLayout(palette_hint_line)
        self.palette_slot = self._fixed_control_slot(self.palette_box, 94)
        layout.addWidget(self.palette_slot)
        self._refresh_palette_buttons()

        self.effect_note = QLabel()
        self.effect_note.setObjectName("effectNote")
        self.effect_note.setWordWrap(True)

        self.effect_info_slot = QWidget()
        self.effect_info_slot.setObjectName("effectInfoSlot")
        self.effect_info_slot.setFixedHeight(90)
        effect_info_layout = QVBoxLayout(self.effect_info_slot)
        effect_info_layout.setContentsMargins(0, 0, 0, 0)
        effect_info_layout.setSpacing(4)
        effect_info_layout.addWidget(self.effect_note)
        effect_info_layout.addStretch()
        layout.addWidget(self.effect_info_slot)

        self.live_checkbox = QCheckBox("Применять изменения сразу")
        self.live_checkbox.setFixedHeight(22)
        self.live_checkbox.stateChanged.connect(self._live_changed)
        layout.addWidget(self.live_checkbox)

        action_line = QHBoxLayout()
        self.apply_button = QPushButton("Применить")
        self.apply_button.setObjectName("primary")
        self.apply_button.clicked.connect(partial(self.apply_state, True))
        self.off_button = QPushButton()
        self.off_button.setObjectName("danger")
        self.off_button.clicked.connect(self.turn_off)
        self.apply_button.setFixedHeight(52)
        self.off_button.setFixedHeight(52)
        action_line.addWidget(self.apply_button, 2)
        action_line.addWidget(self.off_button, 1)
        layout.addLayout(action_line)

        profiles_title = QLabel("ПРОФИЛИ")
        profiles_title.setObjectName("section")
        profiles_title.setFixedHeight(16)
        self.profiles_title = profiles_title
        layout.addWidget(profiles_title)
        self.profiles = QListWidget()
        self.profiles.setFixedHeight(105)
        self.profiles.itemDoubleClicked.connect(self.load_selected_profile)
        layout.addWidget(self.profiles, 1)
        profile_actions = QHBoxLayout()
        self.load_profile_button = QPushButton()
        self.load_profile_button.clicked.connect(self.load_selected_profile)
        self.save_profile_button = QPushButton()
        self.save_profile_button.clicked.connect(self.save_profile)
        self.delete_profile_button = QPushButton("×")
        self.delete_profile_button.setFixedWidth(36)
        self.delete_profile_button.clicked.connect(self.delete_profile)
        for button in (
            self.load_profile_button,
            self.save_profile_button,
            self.delete_profile_button,
        ):
            button.setFixedHeight(44)
        profile_actions.addWidget(self.load_profile_button)
        profile_actions.addWidget(self.save_profile_button)
        profile_actions.addWidget(self.delete_profile_button)
        layout.addLayout(profile_actions)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(controls_container)
        self.controls_scroll = scroll
        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.addWidget(scroll)
        frame = _card(card_layout)
        frame.setFixedWidth(300)
        return frame

    @staticmethod
    def _fixed_control_slot(widget, height):
        """Keep a conditional control's position even while it is hidden."""
        slot = QWidget()
        slot.setFixedHeight(height)
        slot_layout = QVBoxLayout(slot)
        slot_layout.setContentsMargins(0, 0, 0, 0)
        slot_layout.setSpacing(0)
        slot_layout.addWidget(widget)
        return slot

    def _t(self, key, **kwargs):
        return tr(self.language, key, **kwargs)

    def _hardware_mode_text(self, mode_index, field="name"):
        base = HARDWARE_MODE_TRANSLATION_KEYS[int(mode_index)]
        return self._t("{}.{}".format(base, field))

    def _software_mode_text(self, effect, field="name"):
        base = SOFTWARE_MODE_TRANSLATION_KEYS[str(effect)]
        return self._t("{}.{}".format(base, field))

    def _translated_profile_name(self, canonical_name):
        key = BUILTIN_PROFILE_TRANSLATION_KEYS.get(canonical_name)
        return self._t(key) if key else canonical_name

    def _toggle_language(self):
        self.set_language("en" if self.language == "ru" else "ru")

    def set_language(self, language):
        """Switch the existing window in place and persist the preference."""
        language = normalize_language(language)
        self.language = language
        self.store.language = language
        self.store.save()
        self._retranslate_ui()

    def _retranslate_ui(self):
        self.setWindowTitle(self._t("app.title"))
        self.brand_label.setText(self._t("header.brand"))
        self.subtitle_label.clear()
        self.language_button.setText(self._t("button.language"))
        self.modes_title.setText(self._t("section.mode"))
        self.software_modes_title.setText(self._t("section.software"))
        self.mode_footer.clear()
        self.preview_title.setText(self._t("section.preview"))
        self.color_title.setText(self._t("section.color"))
        self.settings_title.setText(self._t("section.settings"))
        self.profiles_title.setText(self._t("section.profiles"))

        for mode in MODES:
            self.mode_buttons[mode.index].setText(
                "{}\n  {}".format(
                    self._hardware_mode_text(mode.index),
                    self._hardware_mode_text(mode.index, "caption"),
                )
            )
        for mode in SOFTWARE_MODES:
            button = self.mode_buttons[mode.button_id]
            button.setText(
                "{}\n  {}".format(
                    self._software_mode_text(mode.effect),
                    self._software_mode_text(mode.effect, "caption"),
                )
            )
            button.setToolTip(self._software_mode_text(mode.effect, "note"))

        self.brightness.setTitle(self._t("control.brightness"))
        self.speed.setTitle(self._t("control.speed"))
        self.direction_label.setText(self._t("control.direction"))
        self.direction_buttons[1].setText(self._t("control.direction_left"))
        self.direction_buttons[2].setText(self._t("control.direction_right"))
        self.zones_label.setText(self._t("control.zones"))
        self.copy_zone_color_button.setText(self._t("control.copy_to_all"))
        self.copy_zone_color_button.setToolTip(
            self._t("control.copy_to_all_tooltip")
        )
        self.live_checkbox.setText(self._t("control.live_apply"))
        self.off_button.setText(self._t("button.off"))
        self.load_profile_button.setText(self._t("button.load"))
        self.save_profile_button.setText(self._t("button.save"))
        self.delete_profile_button.setText(self._t("button.delete"))
        self.delete_profile_button.setToolTip(
            self._t("profile.delete_tooltip")
        )

        state = self.current_state()
        self._refresh_mode_controls(state)
        self._refresh_palette_buttons()
        self.refresh_profiles()
        self._retranslate_tray()
        self._retranslate_status()

    def current_mode(self):
        checked = self.mode_group.checkedId()
        return checked if checked in MODE_BY_INDEX or checked in SOFTWARE_BY_ID else 0

    def current_color(self):
        return self.color_wheel.color()

    def _uses_zone_color_editor(self, selected_mode=None):
        selected_mode = self.current_mode() if selected_mode is None else selected_mode
        software_mode = SOFTWARE_BY_ID.get(selected_mode)
        if software_mode:
            return software_mode.effect in ZONE_COLOR_EFFECTS
        return selected_mode in ZONE_COLOR_MODES

    def _editor_colors(self, selected_mode=None):
        selected_mode = self.current_mode() if selected_mode is None else selected_mode
        software_mode = SOFTWARE_BY_ID.get(selected_mode)
        if software_mode and software_mode.effect == "palette":
            return self.palette_colors
        return self.zone_colors

    def current_state(self):
        color = self.current_color()
        direction = self.direction_group.checkedId()
        zones = tuple(index + 1 for index, check in enumerate(self.zone_checks) if check.isChecked())
        selected_mode = self.current_mode()
        software_mode = SOFTWARE_BY_ID.get(selected_mode)
        if self._uses_zone_color_editor(selected_mode):
            red, green, blue = self._editor_colors(selected_mode)[0]
        else:
            red, green, blue = color.red(), color.green(), color.blue()
        return LightingState(
            mode=selected_mode if selected_mode in MODE_BY_INDEX else 0,
            red=red, green=green, blue=blue,
            brightness=self.brightness.value(), speed=self.speed.value(),
            direction=direction, zones=zones,
            software_effect=software_mode.effect if software_mode else "",
            palette=tuple(self.palette_colors),
            zone_colors=tuple(self.zone_colors),
        ).normalized()

    def load_state(self, state):
        previous_loading = self._loading
        self._loading = True
        state = state.normalized()
        software_mode = SOFTWARE_BY_EFFECT.get(state.software_effect)
        selected_mode = software_mode.button_id if software_mode else state.mode
        self.zone_colors = list(state.zone_colors)
        self.palette_colors = list(state.palette[:4])
        while len(self.palette_colors) < 4:
            self.palette_colors.append(DEFAULT_PALETTE[len(self.palette_colors)])
        self.palette_active_index = 0
        self._refresh_palette_buttons(selected_mode)
        self.palette_buttons[self.palette_active_index].setChecked(True)
        self.mode_buttons[selected_mode].setChecked(True)
        QTimer.singleShot(
            0,
            partial(
                self.mode_scroll.ensureWidgetVisible,
                self.mode_buttons[selected_mode],
                0,
                18,
            ),
        )
        color = (
            self._editor_colors(selected_mode)[self.palette_active_index]
            if self._uses_zone_color_editor(selected_mode)
            else (state.red, state.green, state.blue)
        )
        self.color_wheel.setColor(QColor(*color))
        self.brightness.setValue(state.brightness)
        self.speed.setValue(state.speed)
        self.direction_buttons[state.direction].setChecked(True)
        for index, check in enumerate(self.zone_checks, 1):
            check.setChecked(index in state.zones)
        self._loading = previous_loading
        if not self._loading:
            self._controls_changed()

    def _select_mode(self, mode):
        if self._loading:
            return
        if self._uses_zone_color_editor(mode):
            colors = self._editor_colors(mode)
            self.color_wheel.setColor(QColor(*colors[self.palette_active_index]))
            self._sync_color_fields(self.current_color())
            self._refresh_palette_buttons(mode)
        self._controls_changed()

    def _color_changed(self, color):
        selected_mode = self.current_mode()
        if self._uses_zone_color_editor(selected_mode):
            self._editor_colors(selected_mode)[self.palette_active_index] = (
                color.red(), color.green(), color.blue()
            )
            self._refresh_palette_buttons(selected_mode)
        self._sync_color_fields(color)
        self._controls_changed()

    def _select_palette_slot(self, index):
        self.palette_active_index = max(0, min(3, int(index)))
        color = QColor(*self._editor_colors()[self.palette_active_index])
        self.color_wheel.setColor(color)
        self._sync_color_fields(color)

    def _copy_color_to_all_zones(self):
        if not self._uses_zone_color_editor():
            return
        software_mode = SOFTWARE_BY_ID.get(self.current_mode())
        if software_mode and software_mode.effect == "palette":
            return
        color = self.current_color()
        value = (color.red(), color.green(), color.blue())
        self.zone_colors = [value] * 4
        self._refresh_palette_buttons()
        self._controls_changed()

    def _refresh_palette_buttons(self, selected_mode=None):
        selected_mode = self.current_mode() if selected_mode is None else selected_mode
        colors = self._editor_colors(selected_mode)
        software_mode = SOFTWARE_BY_ID.get(selected_mode)
        tooltip_name = self._t(
            "zone.transition_name"
            if software_mode and software_mode.effect == "palette"
            else "zone.name"
        )
        for index, (button, color) in enumerate(
            zip(getattr(self, "palette_buttons", ()), colors)
        ):
            value = QColor(*color).name().upper()
            button.setStyleSheet(
                "QPushButton#paletteSwatch { background: %s; } "
                "QPushButton#paletteSwatch:checked { border: 3px solid #ffffff; }"
                % value
            )
            button.setToolTip(
                self._t(
                    "zone.tooltip",
                    name=tooltip_name,
                    index=index + 1,
                    color=value,
                )
            )

    def _set_color(self, color):
        self.color_wheel.setColor(color, emit=True)

    def _sync_color_fields(self, color):
        self.hex_input.setText(color.name(QColor.NameFormat.HexRgb).upper())
        self.hex_input.setCursorPosition(0)
        for editor, value in zip(self.rgb_inputs, (color.red(), color.green(), color.blue())):
            editor.setText(str(value))
            editor.setCursorPosition(0)
        self.color_chip.setStyleSheet(
            "background: %s; border: 1px solid rgba(255,255,255,50); border-radius: 10px;" % color.name()
        )

    def _hex_edited(self):
        text = self.hex_input.text().strip()
        if not text.startswith("#"):
            text = "#" + text
        color = QColor(text)
        if color.isValid() and len(text) == 7:
            self._set_color(color)
        else:
            self._sync_color_fields(self.current_color())

    def _rgb_edited(self):
        try:
            values = [max(0, min(255, int(editor.text()))) for editor in self.rgb_inputs]
        except ValueError:
            self._sync_color_fields(self.current_color())
            return
        self._set_color(QColor(*values))

    def _zones_changed(self):
        if self._loading:
            return
        if not any(check.isChecked() for check in self.zone_checks):
            sender = self.sender()
            if sender in self.zone_checks:
                sender.blockSignals(True)
                sender.setChecked(True)
                sender.blockSignals(False)
        self._controls_changed()

    def _live_changed(self):
        if self._loading:
            return
        self.store.live_apply = self.live_checkbox.isChecked()
        self.store.save()
        if self.live_checkbox.isChecked():
            self._schedule_apply()

    def _set_color_editor_enabled(self, enabled):
        enabled = bool(enabled)
        self.color_card.setEnabled(enabled)
        self.color_card_opacity_effect.setOpacity(1.0 if enabled else 0.42)
        self.color_title.setText(
            self._t("section.color" if enabled else "section.color_automatic")
        )

    def _refresh_mode_controls(self, state):
        software_mode = SOFTWARE_BY_EFFECT.get(state.software_effect)
        if software_mode:
            self.mode_caption.setText(
                "{} · {}%".format(
                    self._software_mode_text(software_mode.effect),
                    state.brightness,
                )
            )
            self.speed.setVisible(True)
            self.direction_box.setVisible(software_mode.uses_direction)
            self.zones_box.setVisible(False)
            self._set_color_editor_enabled(True)
            self.palette_box.setVisible(True)
            if state.software_effect == "palette":
                self.palette_label.setText(self._t("control.transition_colors"))
                self.palette_hint.setText(self._t("control.transition_hint"))
                self.copy_zone_color_button.setVisible(False)
            else:
                self.palette_label.setText(self._t("control.zone_colors"))
                self.palette_hint.setText(self._t("control.zone_order_hint"))
                self.copy_zone_color_button.setVisible(True)
            self.effect_note.setText(
                self._software_mode_text(software_mode.effect, "note")
            )
            self.effect_note.setVisible(True)
            symbol = {"aurora": "✦", "comet": "☄", "palette": "◈"}[
                state.software_effect
            ]
            self.apply_button.setText(self._t("button.run", symbol=symbol))
        else:
            spec = MODE_BY_INDEX[state.mode]
            self.mode_caption.setText(
                "{} · {}%".format(
                    self._hardware_mode_text(spec.index),
                    state.brightness,
                )
            )
            self.speed.setVisible(spec.uses_speed)
            self.direction_box.setVisible(spec.uses_direction)
            self.zones_box.setVisible(spec.uses_zones)
            self._set_color_editor_enabled(spec.uses_color)
            self.palette_box.setVisible(spec.uses_color)
            if spec.uses_color:
                self.palette_label.setText(self._t("control.zone_colors"))
                self.palette_hint.setText(self._t("control.zone_order_hint"))
                self.copy_zone_color_button.setVisible(True)
            else:
                self.copy_zone_color_button.setVisible(False)
            distinct_zone_colors = len(set(state.zone_colors)) > 1
            software_zones = state.mode in (1, 4, 5) and distinct_zone_colors
            if software_zones:
                self.effect_note.setText(self._t("control.multicolor_note"))
            self.effect_note.setVisible(software_zones)
            self.apply_button.setText(
                self._t("button.run_four_zones")
                if software_zones
                else self._t("button.apply")
            )

    def _controls_changed(self):
        if self._loading:
            return
        if self._startup_restore_pending and not self._startup_restore_internal:
            self._cancel_startup_restore()
        state = self.current_state()
        self._refresh_mode_controls(state)
        self._refresh_palette_buttons()
        self.preview.setState(state)
        self._sync_color_fields(self.current_color())
        self.store.last_state = state
        if self.live_checkbox.isChecked():
            self._schedule_apply()

    def _schedule_apply(self):
        if not self._loading:
            self.apply_timer.start()

    @staticmethod
    def _state_uses_software_pipeline(state):
        return bool(state.software_effect) or (
            state.mode in ZONE_MODE_EFFECTS
            and len(set(state.zone_colors)) > 1
        )

    @classmethod
    def _startup_state_requires_static_device(cls, state):
        return state.mode == 0 or cls._state_uses_software_pipeline(state)

    def start_startup_restore(self):
        """Restore persisted lighting after a hidden XDG autostart.

        The desktop session may start before udev permissions or either Facer
        character device is ready.  Keep a captured state and retry quietly;
        a real user edit cancels the pending restore so it can never overwrite
        newer choices made after the window was opened.
        """

        if (
            self._worker_stopped
            or self._startup_restore_pending
            or self._startup_restore_in_flight
            or self._startup_restore_completed
        ):
            return False
        self._startup_restore_state = self.store.last_state.normalized()
        self._startup_restore_expected_action = ""
        self._startup_restore_pending = True
        self._startup_restore_in_flight = False
        self.apply_timer.stop()
        self.startup_restore_timer.start(STARTUP_RESTORE_INITIAL_DELAY_MS)
        return True

    def _attempt_startup_restore(self):
        if (
            not self._startup_restore_pending
            or self._startup_restore_in_flight
            or self._worker_stopped
        ):
            return False
        state = self._startup_restore_state
        if state is None:
            self._cancel_startup_restore()
            return False

        status = self.controller.status()
        demo = bool(status.get("demo"))
        ready = demo or bool(
            status.get("available") and status.get("writable")
        )
        if (
            ready
            and not demo
            and self._startup_state_requires_static_device(state)
        ):
            ready = bool(status.get("static_available"))
        if not ready:
            self.startup_restore_timer.start(STARTUP_RESTORE_RETRY_MS)
            return False

        self._startup_restore_in_flight = True
        self._startup_restore_expected_action = (
            "enter_software"
            if self._state_uses_software_pipeline(state)
            else "apply"
        )
        self._startup_restore_internal = True
        try:
            self.load_state(state)
            # load_state may schedule live-apply.  The explicit restore below
            # is the sole writer and its completion is tracked for retries.
            self.apply_timer.stop()
            self.apply_state(False, True)
        finally:
            self._startup_restore_internal = False
        return True

    def _retry_startup_restore(self):
        if not self._startup_restore_pending or self._worker_stopped:
            return
        self._startup_restore_in_flight = False
        self._startup_restore_expected_action = ""
        self.startup_restore_timer.start(STARTUP_RESTORE_RETRY_MS)

    def _complete_startup_restore(self):
        self.startup_restore_timer.stop()
        self._startup_restore_pending = False
        self._startup_restore_in_flight = False
        self._startup_restore_completed = True
        self._startup_restore_expected_action = ""
        self._startup_restore_state = None

    def _cancel_startup_restore(self):
        self.startup_restore_timer.stop()
        self._startup_restore_pending = False
        self._startup_restore_in_flight = False
        self._startup_restore_completed = True
        self._startup_restore_expected_action = ""
        self._startup_restore_state = None

    def _handle_startup_restore_result(self, action, success):
        if (
            not self._startup_restore_pending
            or not self._startup_restore_in_flight
            or action != self._startup_restore_expected_action
        ):
            return
        if success:
            self._complete_startup_restore()
        else:
            self._retry_startup_restore()

    def refresh_status(self):
        if self._status_toast_active:
            return
        status = self.controller.status()
        online = status.get("available") and status.get("writable")
        key = DEVICE_STATUS_TRANSLATION_KEYS.get(status.get("message", ""))
        if key == "status.keyboard_connected":
            self._status_translation = None
            self.status_label.clear()
            self.status_label.hide()
            if getattr(self, "tray_icon", None) is not None:
                self.tray_icon.setToolTip("Facer Studio")
            return
        if key:
            self._set_status_key(key, online, "●  " if online else "○  ")
        else:
            self._set_status(
                ("●  " if online else "○  ") + status.get("message", ""),
                online,
            )

    def _set_status_key(self, key, online, prefix="", **kwargs):
        self._status_translation = (key, bool(online), prefix, dict(kwargs))
        self._display_status(
            prefix + self._translated_status_text(key, kwargs),
            online,
        )

    def _translated_status_text(self, key, kwargs):
        values = dict(kwargs)
        if key == "runtime.message":
            return translate_runtime_message(
                self.language,
                values.get("message", ""),
            )
        title_key = values.pop("_title_key", None)
        if title_key:
            values["title"] = self._t(title_key)
        return self._t(key, **values)

    def _set_status(self, text, online):
        self._status_translation = None
        self._display_status(text, online)

    def _set_runtime_message_status(self, message, online=False, prefix="○  "):
        self._set_status_key(
            "runtime.message",
            online,
            prefix,
            message=str(message),
        )

    def _display_status(self, text, online):
        self._cancel_status_toast()
        self._render_status(text, online)

    def _render_status(self, text, online):
        self.status_label.setText(text)
        self.status_label.show()
        self.status_label.setObjectName("statusOnline" if online else "statusOffline")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        if getattr(self, "tray_icon", None) is not None:
            self.tray_icon.setToolTip(
                "Facer Studio · {}".format(text.lstrip("●○✓↻♪✦☄◈  "))
            )

    def _show_status_toast_key(self, key):
        self._cancel_status_toast()
        self._status_translation = (key, True, "", {})
        self._status_toast_active = True
        self._render_status(self._t(key), True)
        self.status_opacity_effect.setOpacity(0.0)
        self.status_toast_animation.start()

    def _cancel_status_toast(self):
        self.status_toast_animation.stop()
        self._status_toast_active = False
        self.status_opacity_effect.setOpacity(1.0)

    def _finish_status_toast(self):
        if not self._status_toast_active:
            return
        self._status_toast_active = False
        self._status_translation = None
        self.status_opacity_effect.setOpacity(1.0)
        self.status_label.clear()
        self.status_label.hide()
        if getattr(self, "tray_icon", None) is not None:
            self.tray_icon.setToolTip("Facer Studio")
        self.refresh_status()

    def _retranslate_status(self):
        if self._status_translation:
            key, online, prefix, kwargs = self._status_translation
            self._render_status(
                prefix + self._translated_status_text(key, kwargs),
                online,
            )
        else:
            self.refresh_status()

    def apply_state(self, show_dialog=True, startup_restore=False):
        if not startup_restore and self._startup_restore_pending:
            self._cancel_startup_restore()
        state = self.current_state()
        self.store.last_state = state
        self.store.save()
        if state.software_effect in ("aurora", "comet", "palette"):
            self._start_visual_effect(state, show_dialog)
            return True
        zone_effect = ZONE_MODE_EFFECTS.get(state.mode)
        if zone_effect and len(set(state.zone_colors)) > 1:
            self._start_visual_effect(state, show_dialog, zone_effect)
            return True
        self._stop_software_producers()
        self._set_status_key("status.sending", True)
        self.device_worker.submit("apply", state, show_dialog)
        return True

    def turn_off(self):
        if self._startup_restore_pending:
            self._cancel_startup_restore()
        self.apply_timer.stop()
        self._stop_software_producers()
        self._set_status_key("status.turning_off", False)
        self.device_worker.submit("off", self.current_state(), True)

    def _begin_software_session(self):
        self._software_generation_counter += 1
        self._active_software_generation = self._software_generation_counter
        self._software_started = False
        return self._active_software_generation

    def _invalidate_software_session(self):
        generation = self._active_software_generation
        self._active_software_generation = 0
        self._software_started = False
        if generation:
            self.device_worker.cancel_software(generation)

    def _stop_visual_effect(self):
        self.effect_timer.stop()
        self._active_visual_state = None
        self._active_visual_effect = ""
        self._visual_show_dialog = False

    def _stop_software_producers(self):
        self._stop_visual_effect()
        self._invalidate_software_session()

    def _start_visual_effect(self, state, show_dialog, effect=None):
        self.apply_timer.stop()
        self._stop_software_producers()
        self._active_visual_state = state.normalized()
        self._active_visual_effect = effect or state.software_effect
        self._visual_started_at = time.monotonic()
        self._visual_show_dialog = bool(show_dialog)
        self._begin_software_session()
        if self._active_visual_effect in SOFTWARE_BY_EFFECT:
            title_key = "{}.name".format(
                SOFTWARE_MODE_TRANSLATION_KEYS[self._active_visual_effect]
            )
        else:
            title_key = "{}.name".format(
                HARDWARE_MODE_TRANSLATION_KEYS[state.mode]
            )
        self._set_status_key(
            "status.starting_effect",
            True,
            _title_key=title_key,
        )
        self.effect_timer.start()
        self._render_visual_frame()

    def _render_visual_frame(self):
        state = self._active_visual_state
        effect = self._active_visual_effect
        generation = self._active_software_generation
        if state is None or not effect or not generation:
            return
        try:
            frame = render_effect(
                effect,
                time.monotonic() - self._visual_started_at,
                base_color=(state.red, state.green, state.blue),
                speed=state.speed,
                direction=state.direction,
                palette=state.palette,
                zone_colors=(
                    state.zone_colors if len(set(state.zone_colors)) > 1 else None
                ),
            )
        except Exception as error:
            raw_error = str(error)
            message = self._t("status.render_failed", error=raw_error)
            show_dialog = self._visual_show_dialog
            self._stop_software_producers()
            self._set_status_key(
                "status.render_failed",
                False,
                "○  ",
                error=raw_error,
            )
            if show_dialog and message != self._last_error:
                QMessageBox.warning(self, "Facer Studio", message)
            self._last_error = message
            return

        # KeyboardPreview renders deterministic visual effects on its own
        # smoother clock.  Feeding the 5 FPS device frame back into it here
        # would make it alternate between two independent timelines and jump.
        if not self._software_started:
            self._software_started = self.device_worker.submit(
                "enter_software",
                (frame, state.brightness),
                self._visual_show_dialog,
                generation,
            )
        else:
            self.device_worker.submit_frame(frame, generation)

    def _operation_finished(self, success, message, show_dialog, action, generation):
        if action in ("frame", "enter_software"):
            if generation != self._active_software_generation:
                return
        elif self._active_software_generation:
            # A completion from an older firmware/off command must not replace
            # the status of the software effect the user started afterwards.
            return
        self._handle_startup_restore_result(action, success)
        if not success:
            localized_message = translate_runtime_message(self.language, message)
            if action in ("frame", "enter_software"):
                self._stop_software_producers()
            self._set_runtime_message_status(message)
            if show_dialog and localized_message != self._last_error:
                QMessageBox.warning(self, "Facer Studio", localized_message)
            self._last_error = localized_message
        elif action == "frame":
            return
        elif action == "off":
            self._last_error = ""
            self._set_status_key("status.off_sent", False)
        elif action == "enter_software":
            if not self._software_started:
                return
            if self._active_visual_state is None:
                return
            self._last_error = ""
            self._show_status_toast_key("status.settings_applied")
        else:
            self._last_error = ""
            self._show_status_toast_key("status.settings_applied")

    def refresh_profiles(self):
        current_item = self.profiles.currentItem()
        selected = (
            current_item.data(PROFILE_CANONICAL_ROLE)
            if current_item is not None
            else ""
        )
        self.profiles.clear()
        for name in self.store.all_profiles():
            item = QListWidgetItem(self._translated_profile_name(name))
            item.setData(Qt.ItemDataRole.UserRole, name not in BUILTIN_PROFILES)
            item.setData(PROFILE_CANONICAL_ROLE, name)
            if name in BUILTIN_PROFILES:
                item.setToolTip(self._t("profile.builtin_tooltip"))
            self.profiles.addItem(item)
            if name == selected:
                self.profiles.setCurrentItem(item)
        if self.profiles.count() and self.profiles.currentRow() < 0:
            self.profiles.setCurrentRow(0)

    def load_selected_profile(self, item=None):
        item = item if isinstance(item, QListWidgetItem) else self.profiles.currentItem()
        if item is None:
            return
        canonical_name = item.data(PROFILE_CANONICAL_ROLE) or item.text()
        state = self.store.state_for(canonical_name)
        if state:
            self.load_state(state)
            if not self.live_checkbox.isChecked():
                self._set_status_key("profile.loaded", True)

    def save_profile(self):
        name, accepted = QInputDialog.getText(
            self,
            self._t("profile.new_title"),
            self._t("profile.name_prompt"),
        )
        name = name.strip()
        if not accepted or not name:
            return
        builtin_display_names = {
            self._translated_profile_name(profile_name)
            for profile_name in BUILTIN_PROFILES
        }
        if name in BUILTIN_PROFILES or name in builtin_display_names:
            QMessageBox.information(
                self,
                self._t("dialog.warning_title"),
                self._t("profile.builtin_name_taken"),
            )
            return
        self.store.put(name, self.current_state())
        self.refresh_profiles()

    def delete_profile(self):
        item = self.profiles.currentItem()
        if item is None:
            return
        canonical_name = item.data(PROFILE_CANONICAL_ROLE) or item.text()
        if not self.store.remove(canonical_name):
            QMessageBox.information(
                self,
                self._t("dialog.warning_title"),
                self._t("profile.builtin_cannot_delete"),
            )
            return
        self.refresh_profiles()

    def _setup_tray(self):
        self.tray_icon = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False
        tray = QSystemTrayIcon(self.windowIcon(), self)
        menu = QMenu()

        self.tray_open_action = QAction(tray)
        self.tray_open_action.triggered.connect(self.show_window)
        menu.addAction(self.tray_open_action)
        menu.addSeparator()

        self.tray_apply_action = QAction(tray)
        self.tray_apply_action.triggered.connect(
            lambda checked=False: self.apply_state(False)
        )
        menu.addAction(self.tray_apply_action)
        self.tray_off_action = QAction(tray)
        self.tray_off_action.triggered.connect(lambda checked=False: self.turn_off())
        menu.addAction(self.tray_off_action)
        menu.addSeparator()

        self.tray_quit_action = QAction(tray)
        self.tray_quit_action.triggered.connect(self.request_quit)
        menu.addAction(self.tray_quit_action)

        tray.setContextMenu(menu)
        tray.setToolTip("Facer Studio")
        tray.activated.connect(self._tray_activated)
        tray.show()
        self.tray_icon = tray
        self._retranslate_tray()
        return True

    def _retranslate_tray(self):
        if getattr(self, "tray_icon", None) is None:
            return
        self.tray_open_action.setText(self._t("tray.open"))
        self.tray_apply_action.setText(self._t("tray.apply"))
        self.tray_off_action.setText(self._t("tray.off"))
        self.tray_quit_action.setText(self._t("tray.quit"))

    def _tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_window()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def request_quit(self):
        self._quitting = True
        self.shutdown()
        QApplication.instance().quit()

    def shutdown(self):
        self._quitting = True
        self.store.last_state = self.current_state()
        self.store.live_apply = self.live_checkbox.isChecked()
        self.store.save()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self._shutdown_worker()

    def closeEvent(self, event):
        self.store.last_state = self.current_state()
        self.store.live_apply = self.live_checkbox.isChecked()
        self.store.save()
        if self.tray_icon is not None and not self._quitting:
            event.ignore()
            self.hide()
            if not self._tray_notice_shown:
                self.tray_icon.showMessage(
                    self._t("tray.hidden_title"),
                    self._t("tray.hidden_message"),
                    QSystemTrayIcon.MessageIcon.Information,
                    3500,
                )
                self._tray_notice_shown = True
            return
        self._shutdown_worker()
        super().closeEvent(event)

    def _shutdown_worker(self):
        if self._worker_stopped:
            return
        self._worker_stopped = True
        self.startup_restore_timer.stop()
        self._startup_restore_pending = False
        self._startup_restore_in_flight = False
        self.apply_timer.stop()
        self._stop_software_producers()
        self.device_worker.stop()
        self.device_worker.wait()
