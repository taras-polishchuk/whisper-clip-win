from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal

from app.config import AppConfig
from app.runtime_preferences import (
    RuntimeResolution,
    cuda_runtime_available,
    detect_graphics_adapters,
    directml_runtime_available,
    resolve_runtime_preference,
)
from app.services.inference_backends import load_transcription_backend
from app.services.model_download_service import ModelDownloadService


class ModelManager(QObject):
    download_started = Signal()
    download_finished = Signal(str)
    loading_started = Signal()
    model_ready = Signal()
    model_failed = Signal(str)

    def __init__(self, config: AppConfig, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._downloader = ModelDownloadService(config.models_dir)
        self._model = None
        self._worker: threading.Thread | None = None
        self._runtime_resolution: RuntimeResolution | None = None

    def update_config(self, config: AppConfig) -> None:
        self._config = config
        self._downloader = ModelDownloadService(config.models_dir)

    def model_exists(self) -> bool:
        try:
            runtime_resolution = self._resolve_runtime_preference()
        except RuntimeError:
            return False
        if not self._downloader.is_model_downloaded(self._config.model_name, backend=runtime_resolution.actual_backend):
            return False
        if runtime_resolution.actual_backend == "directml":
            return self._downloader.is_export_prepared(self._config.model_name, backend="directml")
        return True

    def initialize_async(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._worker = threading.Thread(target=self._initialize, name="model-manager", daemon=True)
        self._worker.start()

    def require_model(self):
        if self._model is None:
            raise RuntimeError("Whisper model is not loaded yet.")
        return self._model

    def runtime_summary(self) -> str:
        if self._runtime_resolution is None:
            return "Model is ready."
        return self._runtime_resolution.summary

    def shutdown(self) -> None:
        self._worker = None

    def _initialize(self) -> None:
        try:
            self._runtime_resolution = self._resolve_runtime_preference()

            if not self._downloader.is_model_downloaded(
                self._config.model_name,
                backend=self._runtime_resolution.actual_backend,
            ):
                self.download_started.emit()
                model_path = self._downloader.ensure_model(
                    self._config.model_name,
                    backend=self._runtime_resolution.actual_backend,
                )
                self.download_finished.emit(str(model_path))

            self.loading_started.emit()
            self._model = load_transcription_backend(
                model_name=self._config.model_name,
                runtime_resolution=self._runtime_resolution,
                downloader=self._downloader,
            )
            self.model_ready.emit()
        except Exception as exc:  # pragma: no cover - runtime dependent
            self.model_failed.emit(str(exc))

    def _resolve_runtime_preference(self) -> RuntimeResolution:
        return resolve_runtime_preference(
            self._config.device,
            self._config.compute_type,
            detect_graphics_adapters(),
            cuda_runtime_available(),
            directml_runtime_available(),
        )