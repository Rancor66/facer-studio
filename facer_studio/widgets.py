"""Custom-painted controls used by the Qt interface."""

import colorsys
import math

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from .backend import LightingState, SoftwareFrame
from .effects import render_effect


VISUAL_SOFTWARE_EFFECTS = frozenset(("aurora", "comet", "palette"))
ZONE_MODE_EFFECTS = {
    1: "zone_breathing",
    4: "zone_shifting",
    5: "zone_impulse",
}


class ColorWheel(QWidget):
    colorChanged = pyqtSignal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = QColor(145, 55, 255)
        self._image = None
        self._image_size = 0
        self.setMinimumSize(230, 230)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def sizeHint(self):
        return QSize(265, 265)

    def color(self):
        return QColor(self._color)

    def setColor(self, color, emit=False):
        color = QColor(color)
        if not color.isValid():
            return
        self._color = color
        self.update()
        if emit:
            self.colorChanged.emit(QColor(self._color))

    def _geometry(self):
        side = max(20, min(self.width(), self.height()) - 18)
        left = (self.width() - side) / 2
        top = (self.height() - side) / 2
        return QRectF(left, top, side, side)

    def _ensure_image(self, side):
        pixel_side = max(1, int(side))
        if self._image is not None and self._image_size == pixel_side:
            return
        image = QImage(pixel_side, pixel_side, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        center = (pixel_side - 1) / 2
        radius = max(1.0, center)
        for y in range(pixel_side):
            for x in range(pixel_side):
                dx = x - center
                dy = y - center
                saturation = math.hypot(dx, dy) / radius
                if saturation <= 1.0:
                    hue = (math.atan2(dy, dx) / (2 * math.pi)) % 1.0
                    red, green, blue = colorsys.hsv_to_rgb(hue, saturation, 1.0)
                    image.setPixelColor(x, y, QColor.fromRgbF(red, green, blue))
        self._image = image
        self._image_size = pixel_side

    def paintEvent(self, event):
        rect = self._geometry()
        self._ensure_image(rect.width())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#34384b"), 2))
        painter.setBrush(QColor("#0d0f16"))
        painter.drawEllipse(rect.adjusted(-4, -4, 4, 4))
        painter.drawImage(rect, self._image)

        hue = self._color.hsvHueF()
        if hue < 0:
            hue = 0.0
        saturation = self._color.hsvSaturationF()
        angle = hue * 2 * math.pi
        radius = rect.width() / 2
        center = rect.center()
        marker = QPointF(
            center.x() + math.cos(angle) * saturation * radius,
            center.y() + math.sin(angle) * saturation * radius,
        )
        painter.setPen(QPen(QColor("#ffffff"), 3))
        painter.setBrush(self._color)
        painter.drawEllipse(marker, 8, 8)
        painter.setPen(QPen(QColor(0, 0, 0, 130), 1))
        painter.drawEllipse(marker, 5, 5)

    def _pick(self, position):
        rect = self._geometry()
        center = rect.center()
        dx = position.x() - center.x()
        dy = position.y() - center.y()
        radius = rect.width() / 2
        distance = math.hypot(dx, dy)
        if distance > radius + 8:
            return
        saturation = min(1.0, distance / radius)
        hue = (math.atan2(dy, dx) / (2 * math.pi)) % 1.0
        self.setColor(QColor.fromHsvF(hue, saturation, 1.0), emit=True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._pick(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._pick(event.position())


class KeyboardPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = LightingState()
        self.phase = 0.0
        self._effect_elapsed = 0.0
        self._software_frame = None
        self.setMinimumHeight(210)
        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(45)
        self._timer = timer

    def sizeHint(self):
        return QSize(580, 225)

    def setState(self, state):
        previous_effect = self._timed_effect(self.state)
        self.state = state.normalized()
        self._software_frame = None
        if self._timed_effect(self.state) != previous_effect:
            self._effect_elapsed = 0.0
        self._render_visual_effect()
        self.update()

    def setSoftwareFrame(self, frame):
        if not isinstance(frame, SoftwareFrame):
            frame = SoftwareFrame(tuple(frame))
        self._software_frame = frame
        self.update()

    def _tick(self):
        if self._timed_effect(self.state):
            self._effect_elapsed += self._timer.interval() / 1000.0
            self._render_visual_effect()
            self.update()
        elif self.state.mode != 0 or self.state.software_effect:
            direction = -1 if self.state.direction == 1 else 1
            self.phase = (self.phase + direction * (0.006 + self.state.speed * 0.0022)) % 1.0
            self.update()

    @staticmethod
    def _timed_effect(state):
        if state.software_effect in VISUAL_SOFTWARE_EFFECTS:
            return state.software_effect
        if len(set(state.zone_colors)) > 1:
            return ZONE_MODE_EFFECTS.get(state.mode, "")
        return ""

    def _render_visual_effect(self):
        state = self.state
        effect = self._timed_effect(state)
        if not effect:
            return
        self._software_frame = render_effect(
            effect,
            self._effect_elapsed,
            base_color=(state.red, state.green, state.blue),
            speed=state.speed,
            direction=state.direction,
            palette=state.palette,
            zone_colors=(
                state.zone_colors if len(set(state.zone_colors)) > 1 else None
            ),
        )

    def _zone_color(self, zone):
        state = self.state
        if state.mode in (0, 1, 4, 5):
            zone_base = state.zone_colors[zone - 1]
            base = QColor(*zone_base)
        else:
            base = QColor(state.red, state.green, state.blue)
        if self._timed_effect(state):
            color = self._software_frame.zones[zone - 1]
            return QColor(color.red, color.green, color.blue)
        if state.mode == 0:
            if zone not in state.zones:
                return QColor("#20232e")
            return base
        if state.mode == 1:
            level = 0.35 + 0.65 * ((math.sin(self.phase * math.pi * 2) + 1) / 2)
            return QColor.fromRgbF(base.redF() * level, base.greenF() * level, base.blueF() * level)
        if state.mode in (2, 3):
            return QColor.fromHsvF((self.phase + zone * 0.18) % 1.0, 0.78, 1.0)
        if state.mode == 4:
            hue = base.hsvHueF()
            if hue < 0:
                hue = 0
            return QColor.fromHsvF((hue + self.phase * 0.35 + zone * 0.025) % 1.0, 0.78, 1.0)
        pulse = 0.32 + 0.68 * ((math.sin((self.phase + abs(2.5 - zone) * 0.16) * math.pi * 2) + 1) / 2)
        return QColor.fromRgbF(base.redF() * pulse, base.greenF() * pulse, base.blueF() * pulse)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(12, 12, self.width() - 24, self.height() - 24)

        body_path = QPainterPath()
        body_path.addRoundedRect(area, 22, 22)
        painter.fillPath(body_path, QColor("#08090d"))
        painter.setPen(QPen(QColor("#2b2e3d"), 1.5))
        painter.drawPath(body_path)

        inner = area.adjusted(18, 22, -18, -24)
        gap = 8
        zone_width = (inner.width() - 3 * gap) / 4
        for index in range(4):
            zone_rect = QRectF(inner.left() + index * (zone_width + gap), inner.top(), zone_width, inner.height())
            color = self._zone_color(index + 1)
            glow = QColor(color)
            glow.setAlpha(46 + int(self.state.brightness * 1.25))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawRoundedRect(zone_rect.adjusted(-3, -3, 3, 3), 12, 12)

            gradient = QLinearGradient(zone_rect.topLeft(), zone_rect.bottomRight())
            dark = QColor(color).darker(270)
            dark.setAlpha(220)
            lit = QColor(color)
            lit.setAlpha(65 + int(self.state.brightness * 1.55))
            gradient.setColorAt(0, dark)
            gradient.setColorAt(0.52, lit)
            gradient.setColorAt(1, QColor("#11131a"))
            painter.setBrush(gradient)
            painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 145), 1))
            painter.drawRoundedRect(zone_rect, 9, 9)

            painter.setPen(QPen(QColor(255, 255, 255, 75), 1))
            rows, columns = 4, 5
            key_gap = 5
            key_width = (zone_rect.width() - 20 - (columns - 1) * key_gap) / columns
            key_height = (zone_rect.height() - 18 - (rows - 1) * key_gap) / rows
            for row in range(rows):
                for column in range(columns):
                    key = QRectF(
                        zone_rect.left() + 10 + column * (key_width + key_gap),
                        zone_rect.top() + 9 + row * (key_height + key_gap),
                        key_width,
                        key_height,
                    )
                    painter.drawRoundedRect(key, 2.5, 2.5)

        painter.setPen(QColor("#676b7e"))
        painter.drawText(
            QRectF(area.left(), area.bottom() - 21, area.width(), 16),
            Qt.AlignmentFlag.AlignCenter,
            "4-ZONE RGB",
        )
