from __future__ import annotations

from PySide6.QtCore import QObject, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from app.models.app_state import AppState


STATE_LABELS = {
    AppState.BOOTING: "Starting",
    AppState.CHECKING_ENV: "Checking runtime",
    AppState.DOWNLOADING_MODEL: "Downloading model",
    AppState.LOADING_MODEL: "Loading model",
    AppState.IDLE: "Ready",
    AppState.RECORDING: "Recording",
    AppState.STOPPING_RECORDING: "Finalizing audio",
    AppState.TRANSCRIBING: "Transcribing",
    AppState.PASTING: "Pasting",
    AppState.CLIPBOARD_ONLY: "Copied to clipboard",
    AppState.ERROR: "Error",
}

STATE_COLORS = {
    AppState.BOOTING: "#64748b",
    AppState.CHECKING_ENV: "#0ea5e9",
    AppState.DOWNLOADING_MODEL: "#0ea5e9",
    AppState.LOADING_MODEL: "#38bdf8",
    AppState.IDLE: "#94a3b8",
    AppState.RECORDING: "#ef4444",
    AppState.STOPPING_RECORDING: "#f97316",
    AppState.TRANSCRIBING: "#2563eb",
    AppState.PASTING: "#16a34a",
    AppState.CLIPBOARD_ONLY: "#eab308",
    AppState.ERROR: "#dc2626",
}


class TrayController(QObject):
    toggle_requested = Signal()
    settings_requested = Signal()
    exit_requested = Signal()

    def __init__(self, app_name: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tray = QSystemTrayIcon(self)
        self._menu = QMenu()
        self._toggle_action = self._menu.addAction("Start Recording")
        self._toggle_action.triggered.connect(self.toggle_requested.emit)
        self._menu.addSeparator()
        self._settings_action = self._menu.addAction("Settings")
        self._settings_action.triggered.connect(self.settings_requested.emit)
        self._exit_action = self._menu.addAction("Exit")
        self._exit_action.triggered.connect(self.exit_requested.emit)

        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.setToolTip(f"{app_name} - Starting")
        self.update_state(AppState.BOOTING)

    def show(self) -> None:
        self._tray.show()

    def update_state(self, state: AppState, detail: str | None = None) -> None:
        label = STATE_LABELS.get(state, state.value.replace("_", " ").title())
        self._tray.setIcon(self._build_icon(state))
        tooltip = f"WhisperClip - {label}"
        if detail:
            tooltip = f"{tooltip}\n{detail}"
        self._tray.setToolTip(tooltip)

        can_toggle = state in {AppState.IDLE, AppState.RECORDING}
        self._toggle_action.setEnabled(can_toggle)
        self._toggle_action.setText("Stop Recording" if state == AppState.RECORDING else "Start Recording")

    def show_message(
        self,
        title: str,
        message: str,
        icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.Information,
        timeout: int = 3000,
    ) -> None:
        self._tray.showMessage(title, message, icon, timeout)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick} and self._toggle_action.isEnabled():
            self.toggle_requested.emit()

    def _build_icon(self, state: AppState) -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(STATE_COLORS[state]))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(8, 8, 48, 48))
        painter.end()
        return QIcon(pixmap)