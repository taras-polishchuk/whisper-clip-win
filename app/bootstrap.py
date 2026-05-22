from __future__ import annotations

import ctypes
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from app.config import AppConfig
from app.logging_setup import configure_logging
from app.models.app_state import AppEvent, AppState, PasteMode
from app.models.dto import FailureInfo, TranscriptionResult
from app.release import APP_DISPLAY_NAME, APP_MUTEX_NAME, APP_PUBLISHER, APP_VERSION
from app.services.audio_capture_service import AudioCaptureService
from app.services.focus_and_paste_service import FocusAndPasteService
from app.services.hotkey_service import GlobalHotkeyService
from app.services.model_manager import ModelManager
from app.services.notification_service import NotificationService
from app.services.startup_service import StartupService
from app.services.transcription_service import TranscriptionService
from app.state_machine import AppStateMachine
from app.ui.overlay_controller import OverlayController
from app.ui.settings_window import SettingsWindow
from app.ui.tray_controller import TrayController


class SingleInstanceGuard:
    ERROR_ALREADY_EXISTS = 183

    def __init__(self, name: str) -> None:
        self._name = name
        self._handle = None

    def acquire(self) -> bool:
        if os.name != "nt":
            return True

        self._handle = ctypes.windll.kernel32.CreateMutexW(None, False, self._name)
        return ctypes.windll.kernel32.GetLastError() != self.ERROR_ALREADY_EXISTS


class WhisperClipController(QObject):
    def __init__(self, app: QApplication, config: AppConfig) -> None:
        super().__init__()
        self._app = app
        self._config = config
        self._state_machine = AppStateMachine()
        self._logger = logging.getLogger("whisper_clip")

        self._tray = TrayController(config.app_name)
        self._overlay = OverlayController(config.overlay_enabled)
        self._settings = SettingsWindow(config)
        self._notifications = NotificationService(self._tray)

        self._audio = AudioCaptureService(config)
        self._model_manager = ModelManager(config)
        self._transcriber = TranscriptionService(self._model_manager, config)
        self._hotkeys = GlobalHotkeyService(config.hotkey)
        self._startup = StartupService(config.app_name, Path(sys.argv[0]).resolve())
        self._paste_service = FocusAndPasteService(config.app_name)
        self._paste_service.set_own_window_handles_provider(self._own_window_handles)
        self._pending_audio_path: Path | None = None

        self._connect_signals()

    def start(self) -> None:
        self._tray.show()
        self._dispatch(AppEvent.APP_STARTED)
        self._hotkeys.register()
        QTimer.singleShot(0, self._initialize_runtime)

    def shutdown(self) -> None:
        self._hotkeys.unregister()
        self._audio.cancel()
        self._model_manager.shutdown()
        self._app.quit()

    def _connect_signals(self) -> None:
        self._tray.toggle_requested.connect(self._handle_toggle)
        self._tray.settings_requested.connect(self._open_settings)
        self._tray.exit_requested.connect(self.shutdown)
        self._settings.config_saved.connect(self._apply_config)

        self._hotkeys.activated.connect(self._handle_toggle)
        self._hotkeys.registration_failed.connect(self._handle_nonfatal_error)

        self._audio.recording_started.connect(self._handle_recording_started)
        self._audio.recording_stopped.connect(self._handle_audio_ready)
        self._audio.recording_failed.connect(self._handle_nonfatal_error)

        self._model_manager.download_started.connect(self._handle_download_started)
        self._model_manager.download_finished.connect(self._handle_download_finished)
        self._model_manager.loading_started.connect(self._handle_loading_started)
        self._model_manager.model_ready.connect(self._handle_model_ready)
        self._model_manager.model_failed.connect(self._handle_fatal_error)

        self._transcriber.started.connect(self._handle_transcription_started)
        self._transcriber.finished.connect(self._handle_transcription_ready)
        self._transcriber.empty.connect(self._handle_transcription_empty)
        self._transcriber.failed.connect(self._handle_nonfatal_error)

    def _initialize_runtime(self) -> None:
        self._sync_startup_setting()
        if not self._model_manager.model_exists():
            self._dispatch(AppEvent.MODEL_MISSING)
        self._model_manager.initialize_async()

    def _handle_toggle(self) -> None:
        transition = self._dispatch(AppEvent.HOTKEY_PRESSED)
        if not transition.changed:
            self._notifications.info("WhisperClip", "Busy right now. Wait for the current action to finish.")
            return

        if transition.to_state == AppState.RECORDING:
            self._audio.start()
        elif transition.to_state == AppState.STOPPING_RECORDING:
            self._audio.stop()

    def _handle_recording_started(self, path: str) -> None:
        self._pending_audio_path = Path(path)
        self._notifications.info("WhisperClip", "Recording started.")

    def _handle_audio_ready(self, path: str) -> None:
        audio_path = Path(path)
        self._pending_audio_path = audio_path
        self._dispatch(AppEvent.AUDIO_READY, audio_path)
        self._transcriber.transcribe_async(audio_path)

    def _handle_download_started(self) -> None:
        self._notifications.info("WhisperClip", "Downloading model for the first run.")

    def _handle_download_finished(self, model_path: str) -> None:
        self._dispatch(AppEvent.MODEL_DOWNLOAD_COMPLETED, model_path)

    def _handle_loading_started(self) -> None:
        if self._state_machine.state in {AppState.CHECKING_ENV, AppState.DOWNLOADING_MODEL}:
            self._dispatch(AppEvent.ENV_OK)

    def _handle_model_ready(self) -> None:
        self._dispatch(AppEvent.MODEL_LOADED)
        self._notifications.info("WhisperClip", self._model_manager.runtime_summary())

    def _handle_transcription_started(self, path: str) -> None:
        self._logger.info("Transcribing %s", path)

    def _handle_transcription_ready(self, result: TranscriptionResult) -> None:
        self._dispatch(AppEvent.TRANSCRIPTION_READY, result)
        paste_result = self._paste_service.paste_or_copy(
            result.text,
            allow_autopaste=self._config.autopaste_enabled,
        )
        if paste_result.mode == PasteMode.PASTED and self._config.autopaste_enabled:
            self._dispatch(AppEvent.PASTE_SUCCEEDED, paste_result)
            self._notifications.info("WhisperClip", "Transcript pasted into the focused window.")
        else:
            self._dispatch(AppEvent.PASTE_SKIPPED, paste_result)
            self._notifications.warning("WhisperClip", "Transcript copied to clipboard.")
            QTimer.singleShot(750, lambda: self._dispatch(AppEvent.RESET))
        self._cleanup_audio(result.audio_path)

    def _handle_transcription_empty(self) -> None:
        self._dispatch(AppEvent.TRANSCRIPTION_EMPTY)
        self._cleanup_audio(self._pending_audio_path)
        self._notifications.warning("WhisperClip", "No speech was recognized.")

    def _handle_nonfatal_error(self, message: str) -> None:
        failure = FailureInfo(message=message, recoverable=True)
        self._dispatch(AppEvent.FAILURE, failure)
        self._notifications.warning("WhisperClip", message)
        QTimer.singleShot(1200, lambda: self._dispatch(AppEvent.RESET))

    def _handle_fatal_error(self, message: str) -> None:
        failure = FailureInfo(message=message, recoverable=False)
        self._dispatch(AppEvent.FAILURE, failure)
        self._notifications.error("WhisperClip", message)

    def _open_settings(self) -> None:
        self._settings.reload(self._config)
        self._settings.show()
        self._settings.raise_()
        self._settings.activateWindow()

    def _apply_config(self, updated: AppConfig) -> None:
        previous_hotkey = self._config.hotkey
        previous_start_on_login = self._config.start_on_login
        previous_runtime = (self._config.model_name, self._config.device, self._config.compute_type)
        self._config = updated
        self._overlay.set_enabled(updated.overlay_enabled)
        self._audio.update_config(updated)
        self._model_manager.update_config(updated)
        self._transcriber.update_config(updated)

        if updated.hotkey != previous_hotkey:
            self._hotkeys.update_hotkey(updated.hotkey)

        if updated.start_on_login != previous_start_on_login:
            self._sync_startup_setting()

        if (updated.model_name, updated.device, updated.compute_type) != previous_runtime:
            message = "Settings saved. Decode and text rules apply immediately. Restart to apply model or device changes."
        else:
            message = "Settings saved. New transcription settings apply immediately."
        self._notifications.info("WhisperClip", message)

    def _dispatch(self, event: AppEvent, payload: object | None = None):
        transition = self._state_machine.dispatch(event, payload)
        self._tray.update_state(transition.to_state)
        self._overlay.set_state(transition.to_state)
        self._logger.info(
            "state transition: %s --(%s)--> %s",
            transition.from_state.value,
            transition.event.value,
            transition.to_state.value,
        )
        return transition

    def _cleanup_audio(self, path: Path | None) -> None:
        if not path:
            return
        path.unlink(missing_ok=True)
        if self._pending_audio_path == path:
            self._pending_audio_path = None

    def _own_window_handles(self) -> list[int]:
        handles = [self._overlay.native_handle()]
        if self._settings.isVisible():
            handles.append(int(self._settings.winId()))
        return [handle for handle in handles if handle]

    def _sync_startup_setting(self) -> None:
        try:
            self._startup.sync(self._config.start_on_login)
        except Exception as exc:  # pragma: no cover - Windows registry dependent
            self._handle_nonfatal_error(f"Unable to update Windows startup setting: {exc}")


def bootstrap() -> int:
    config = AppConfig.load()
    config.ensure_runtime_dirs()
    configure_logging(config.log_dir)
    guard = SingleInstanceGuard(APP_MUTEX_NAME)
    if not guard.acquire():
        logging.getLogger("whisper_clip").warning("WhisperClip is already running.")
        return 1

    app = QApplication(sys.argv)
    app.setApplicationName(config.app_name)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_PUBLISHER)
    app.setQuitOnLastWindowClosed(False)

    controller = WhisperClipController(app, config)
    controller.start()
    return app.exec()