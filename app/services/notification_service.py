from __future__ import annotations

import logging

from PySide6.QtWidgets import QSystemTrayIcon

from app.ui.tray_controller import TrayController


class NotificationService:
    def __init__(self, tray: TrayController) -> None:
        self._tray = tray
        self._logger = logging.getLogger("whisper_clip.notifications")

    def info(self, title: str, message: str) -> None:
        self._logger.info("%s: %s", title, message)
        self._tray.show_message(title, message, QSystemTrayIcon.Information)

    def warning(self, title: str, message: str) -> None:
        self._logger.warning("%s: %s", title, message)
        self._tray.show_message(title, message, QSystemTrayIcon.Warning)

    def error(self, title: str, message: str) -> None:
        self._logger.error("%s: %s", title, message)
        self._tray.show_message(title, message, QSystemTrayIcon.Critical)