from __future__ import annotations

import threading
import wave
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, Signal

from app.config import AppConfig

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional at import time
    np = None

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover - optional at import time
    sd = None


def list_input_device_names() -> list[str]:
    if sd is None:
        return ["Default"]

    devices = [device for device in sd.query_devices() if device.get("max_input_channels", 0) > 0]
    names = [device["name"] for device in devices]
    return ["Default", *names]


class AudioCaptureService(QObject):
    recording_started = Signal(str)
    recording_stopped = Signal(str)
    recording_failed = Signal(str)

    def __init__(self, config: AppConfig, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._frames: list["np.ndarray"] = []
        self._lock = threading.Lock()
        self._stream = None
        self._recording_path: Path | None = None

    def update_config(self, config: AppConfig) -> None:
        self._config = config

    def start(self) -> None:
        if sd is None or np is None:
            self.recording_failed.emit("sounddevice or numpy is not installed.")
            return

        if self._stream is not None:
            self.recording_failed.emit("Recording is already active.")
            return

        self._config.ensure_runtime_dirs()
        self._recording_path = self._config.temp_dir / f"recording_{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex}.wav"
        self._frames = []

        try:
            self._stream = sd.InputStream(
                samplerate=self._config.sample_rate,
                channels=self._config.channels,
                dtype="int16",
                device=self._config.microphone_device or None,
                callback=self._audio_callback,
            )
            self._stream.start()
            self.recording_started.emit(str(self._recording_path))
        except Exception as exc:  # pragma: no cover - hardware dependent
            self._stream = None
            self.recording_failed.emit(str(exc))

    def stop(self) -> None:
        if self._stream is None or self._recording_path is None:
            self.recording_failed.emit("Recording is not active.")
            return

        try:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        except Exception as exc:  # pragma: no cover - hardware dependent
            self.recording_failed.emit(str(exc))
            return

        with self._lock:
            frames = list(self._frames)

        if not frames:
            self.recording_failed.emit("No audio frames were captured.")
            return

        audio = np.concatenate(frames, axis=0)
        self._write_wave(self._recording_path, audio)
        path = str(self._recording_path)
        self._recording_path = None
        self._frames = []
        self.recording_stopped.emit(path)

    def cancel(self) -> None:
        if self._stream is not None:
            self._stream.abort()
            self._stream.close()
            self._stream = None
        self._frames = []
        if self._recording_path and self._recording_path.exists():
            self._recording_path.unlink(missing_ok=True)
        self._recording_path = None

    def _audio_callback(self, indata, frames, time_info, status) -> None:  # pragma: no cover - callback
        if status:
            return
        with self._lock:
            self._frames.append(indata.copy())

    def _write_wave(self, path: Path, audio) -> None:
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(self._config.channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self._config.sample_rate)
            wav_file.writeframes(audio.astype("int16").tobytes())