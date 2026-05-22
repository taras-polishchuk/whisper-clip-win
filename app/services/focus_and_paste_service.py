from __future__ import annotations

import ctypes
import os
import time
from collections.abc import Callable, Iterable

from PySide6.QtGui import QGuiApplication

from app.models.app_state import PasteMode
from app.models.dto import PasteResult

try:
    import pyperclip
except ImportError:  # pragma: no cover - optional at import time
    pyperclip = None


class FocusAndPasteService:
    def __init__(self, app_name: str) -> None:
        self._app_name = app_name
        self._own_window_handles_provider: Callable[[], Iterable[int]] = lambda: []

    def set_own_window_handles_provider(self, provider: Callable[[], Iterable[int]]) -> None:
        self._own_window_handles_provider = provider

    def paste_or_copy(self, text: str, allow_autopaste: bool = True) -> PasteResult:
        self.copy_to_clipboard(text)

        if not allow_autopaste:
            return PasteResult(mode=PasteMode.CLIPBOARD_ONLY)

        if os.name != "nt":
            return PasteResult(mode=PasteMode.CLIPBOARD_ONLY)

        user32 = ctypes.windll.user32
        hwnd = int(user32.GetForegroundWindow())
        own_handles = {int(handle) for handle in self._own_window_handles_provider() if handle}

        if not hwnd or hwnd in own_handles or not self._is_eligible_target(hwnd):
            return PasteResult(mode=PasteMode.CLIPBOARD_ONLY, target_window=hwnd or None)

        time.sleep(0.03)
        self._send_ctrl_v()
        return PasteResult(mode=PasteMode.PASTED, target_window=hwnd)

    def copy_to_clipboard(self, text: str) -> None:
        app = QGuiApplication.instance()
        if app is not None:
            QGuiApplication.clipboard().setText(text)
            return
        if pyperclip is None:
            raise RuntimeError("No clipboard provider is available.")
        pyperclip.copy(text)

    def _is_eligible_target(self, hwnd: int) -> bool:
        user32 = ctypes.windll.user32
        return bool(user32.IsWindow(hwnd) and user32.IsWindowVisible(hwnd))

    def _send_ctrl_v(self) -> None:
        user32 = ctypes.windll.user32
        keyup = 0x0002
        user32.keybd_event(0x11, 0, 0, 0)
        user32.keybd_event(0x56, 0, 0, 0)
        user32.keybd_event(0x56, 0, keyup, 0)
        user32.keybd_event(0x11, 0, keyup, 0)