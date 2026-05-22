from __future__ import annotations

import math
import os

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from app.models.app_state import AppState


OVERLAY_SIZE = 36
OVERLAY_MARGIN = 20


class OverlayController(QWidget):
    def __init__(self, enabled: bool = True) -> None:
        super().__init__(
            None,
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus,
        )
        self._enabled = enabled
        self._state = AppState.BOOTING
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setWindowOpacity(0.86)
        self.resize(OVERLAY_SIZE, OVERLAY_SIZE)
        self.reposition()
        self._update_visibility()

    def native_handle(self) -> int | None:
        if os.name != "nt":
            return None
        return int(self.winId())

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._update_visibility()

    def set_state(self, state: AppState) -> None:
        self._state = state
        self._update_visibility()
        self.update()

    def reposition(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        geometry = screen.availableGeometry()
        self.move(geometry.right() - self.width() - OVERLAY_MARGIN, geometry.top() + OVERLAY_MARGIN)

    def _tick(self) -> None:
        self._phase += 0.15
        self.update()

    def _update_visibility(self) -> None:
        should_show = self._enabled
        if should_show:
            self.show()
            self.raise_()
        else:
            self.hide()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        center = QPointF(self.width() / 2, self.height() / 2)
        shell_rect = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)

        self._draw_shell(painter, shell_rect)

        if self._state == AppState.RECORDING:
            self._draw_recording(painter, center)
        elif self._state in {AppState.TRANSCRIBING, AppState.DOWNLOADING_MODEL, AppState.LOADING_MODEL}:
            self._draw_loader(painter, center)
        elif self._state == AppState.ERROR:
            self._draw_error(painter, center)
        else:
            self._draw_idle(painter, center)

    def _draw_shell(self, painter: QPainter, shell_rect: QRectF) -> None:
        painter.setPen(QPen(QColor(255, 255, 255, 34), 1.0))
        painter.setBrush(QColor(15, 23, 42, 92))
        painter.drawEllipse(shell_rect)

    def _draw_idle(self, painter: QPainter, center: QPointF) -> None:
        painter.setPen(QPen(QColor(148, 163, 184, 68), 1.2))
        painter.setBrush(QColor(148, 163, 184, 112))
        painter.drawEllipse(center, 5.0, 5.0)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 170))
        painter.drawEllipse(center, 2.1, 2.1)

    def _draw_recording(self, painter: QPainter, center: QPointF) -> None:
        pulse_radius = 6.0 + (math.sin(self._phase) + 1.0) * 1.8
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(248, 113, 113, 46))
        painter.drawEllipse(center, pulse_radius + 3.4, pulse_radius + 3.4)
        painter.setBrush(QColor(239, 68, 68, 108))
        painter.drawEllipse(center, pulse_radius, pulse_radius)
        painter.setBrush(QColor(254, 226, 226, 235))
        painter.drawEllipse(center, 3.1, 3.1)

    def _draw_loader(self, painter: QPainter, center: QPointF) -> None:
        ring_rect = QRectF(8.0, 8.0, self.width() - 16.0, self.height() - 16.0)
        track_pen = QPen(QColor(148, 163, 184, 44), 3.0)
        track_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(track_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(ring_rect, 0, 360 * 16)

        active_pen = QPen(QColor(56, 189, 248, 214), 3.0)
        active_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(active_pen)
        start_angle = int((self._phase * 115) % 360)
        span_angle = 126
        painter.drawArc(ring_rect, -start_angle * 16, -span_angle * 16)

        orbit_radius = ring_rect.width() / 2.0
        orbit_angle = math.radians(start_angle + span_angle)
        indicator = QPointF(
            center.x() + math.cos(-orbit_angle) * orbit_radius,
            center.y() + math.sin(-orbit_angle) * orbit_radius,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(125, 211, 252, 232))
        painter.drawEllipse(indicator, 2.2, 2.2)
        painter.setBrush(QColor(255, 255, 255, 112))
        painter.drawEllipse(center, 1.4, 1.4)

    def _draw_error(self, painter: QPainter, center: QPointF) -> None:
        ring_rect = QRectF(8.5, 8.5, self.width() - 17.0, self.height() - 17.0)
        painter.setBrush(Qt.NoBrush)
        error_pen = QPen(QColor(220, 38, 38, 190), 2.6)
        error_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(error_pen)
        painter.drawEllipse(ring_rect)
        painter.drawLine(QPointF(center.x(), center.y() - 4.8), QPointF(center.x(), center.y() + 2.2))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(254, 202, 202, 230))
        painter.drawEllipse(QPointF(center.x(), center.y() + 5.6), 1.4, 1.4)