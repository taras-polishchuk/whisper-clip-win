from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes

from PySide6.QtCore import QObject, Signal


MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

MODIFIER_MAP = {
    "ALT": MOD_ALT,
    "CTRL": MOD_CONTROL,
    "CONTROL": MOD_CONTROL,
    "SHIFT": MOD_SHIFT,
    "WIN": MOD_WIN,
    "META": MOD_WIN,
    "SUPER": MOD_WIN,
}

SPECIAL_KEYS = {
    "SPACE": 0x20,
    "TAB": 0x09,
    "ENTER": 0x0D,
    "ESC": 0x1B,
}
SPECIAL_KEYS.update({f"F{index}": 0x6F + index for index in range(1, 25)})


def parse_hotkey(hotkey: str) -> tuple[int, int]:
    parts = [part.strip().upper() for part in hotkey.split("+") if part.strip()]
    if len(parts) < 2:
        raise ValueError(f"Hotkey '{hotkey}' must include at least one modifier and one key.")

    modifiers = 0
    for part in parts[:-1]:
        if part not in MODIFIER_MAP:
            raise ValueError(f"Unsupported modifier '{part}'.")
        modifiers |= MODIFIER_MAP[part]

    key_token = parts[-1]
    if len(key_token) == 1 and key_token.isalpha():
        virtual_key = ord(key_token)
    elif len(key_token) == 1 and key_token.isdigit():
        virtual_key = ord(key_token)
    else:
        virtual_key = SPECIAL_KEYS.get(key_token)

    if not virtual_key:
        raise ValueError(f"Unsupported hotkey key '{key_token}'.")

    return modifiers, virtual_key


class GlobalHotkeyService(QObject):
    activated = Signal()
    registration_failed = Signal(str)

    def __init__(self, hotkey: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._hotkey = hotkey
        self._hotkey_id = 1
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._running = False
        self._registered = False
        self._registration_error: str | None = None

    @property
    def hotkey(self) -> str:
        return self._hotkey

    def register(self) -> bool:
        if os.name != "nt":
            self.registration_failed.emit("Global hotkeys are only available on Windows.")
            return False

        if self._registered:
            return True

        modifiers, virtual_key = parse_hotkey(self._hotkey)
        ready = threading.Event()
        self._running = True
        self._thread = threading.Thread(
            target=self._message_loop,
            args=(modifiers, virtual_key, ready),
            name="global-hotkey",
            daemon=True,
        )
        self._thread.start()
        ready.wait(timeout=2)

        if self._registration_error:
            self.registration_failed.emit(self._registration_error)
        return self._registered

    def unregister(self) -> None:
        if os.name != "nt" or not self._thread:
            self._registered = False
            return

        self._running = False
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._thread.join(timeout=1.5)
        self._thread = None
        self._thread_id = None
        self._registered = False

    def update_hotkey(self, hotkey: str) -> bool:
        self.unregister()
        self._hotkey = hotkey
        self._registration_error = None
        return self.register()

    def _message_loop(self, modifiers: int, virtual_key: int, ready: threading.Event) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()

        if not user32.RegisterHotKey(None, self._hotkey_id, modifiers, virtual_key):
            self._registration_error = f"Unable to register hotkey '{self._hotkey}'."
            self._running = False
            ready.set()
            return

        self._registered = True
        ready.set()
        message = wintypes.MSG()

        while self._running:
            result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
            if result <= 0:
                break
            if message.message == WM_HOTKEY and message.wParam == self._hotkey_id:
                self.activated.emit()

        user32.UnregisterHotKey(None, self._hotkey_id)