from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import winreg
except ImportError:  # pragma: no cover - only available on Windows
    winreg = None


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


class StartupService:
    def __init__(self, app_name: str, entrypoint: Path) -> None:
        self._app_name = app_name
        self._entrypoint = entrypoint

    def sync(self, enabled: bool) -> bool:
        if os.name != "nt" or winreg is None:
            return False

        if enabled:
            self._set_run_value(self._build_command())
        else:
            self._delete_run_value()
        return True

    def _build_command(self) -> str:
        if getattr(sys, "frozen", False):
            return f'"{Path(sys.executable).resolve()}"'

        python_executable = Path(sys.executable).resolve()
        pythonw = python_executable.with_name("pythonw.exe")
        launcher = pythonw if pythonw.exists() else python_executable
        return f'"{launcher}" "{self._entrypoint}"'

    def _set_run_value(self, command: str) -> None:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, self._app_name, 0, winreg.REG_SZ, command)

    def _delete_run_value(self) -> None:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, self._app_name)
            except FileNotFoundError:
                return