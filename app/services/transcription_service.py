from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from app.config import AppConfig
from app.models.dto import TranscriptionResult
from app.services.model_manager import ModelManager
from app.text import build_runtime_prompt, postprocess_transcript


class TranscriptionService(QObject):
    started = Signal(str)
    finished = Signal(object)
    empty = Signal()
    failed = Signal(str)

    def __init__(self, model_manager: ModelManager, config: AppConfig, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._model_manager = model_manager
        self._config = config
        self._worker: threading.Thread | None = None

    def update_config(self, config: AppConfig) -> None:
        self._config = config

    def transcribe_async(self, audio_path: Path) -> None:
        if self._worker and self._worker.is_alive():
            self.failed.emit("Transcription is already running.")
            return
        self.started.emit(str(audio_path))
        self._worker = threading.Thread(
            target=self._transcribe,
            args=(audio_path,),
            name="transcription",
            daemon=True,
        )
        self._worker.start()

    def _transcribe(self, audio_path: Path) -> None:
        try:
            model = self._model_manager.require_model()
            started_at = time.perf_counter()
            prompt = build_runtime_prompt(self._config.initial_prompt, self._config.custom_terms)
            transcribe_kwargs = {
                "language": self._config.language,
                "initial_prompt": prompt,
                "beam_size": self._config.beam_size,
                "temperature": self._config.temperature,
                "condition_on_previous_text": self._config.condition_on_previous_text,
                "vad_filter": self._config.vad_filter,
            }
            if self._config.vad_filter:
                transcribe_kwargs["vad_parameters"] = {
                    "min_silence_duration_ms": self._config.vad_min_silence_duration_ms,
                }

            segments, info = model.transcribe(
                str(audio_path),
                **transcribe_kwargs,
            )
            text = postprocess_transcript(
                (segment.text for segment in segments),
                self._config.replacement_rules,
            )
            if not text:
                self.empty.emit()
                return

            result = TranscriptionResult(
                text=text,
                language=getattr(info, "language", self._config.language),
                elapsed_seconds=time.perf_counter() - started_at,
                audio_path=audio_path,
            )
            self.finished.emit(result)
        except Exception as exc:  # pragma: no cover - runtime dependent
            self.failed.emit(str(exc))