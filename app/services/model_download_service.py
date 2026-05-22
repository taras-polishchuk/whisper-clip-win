from __future__ import annotations

from pathlib import Path

try:
    from huggingface_hub import snapshot_download
except ImportError:  # pragma: no cover - optional at import time
    snapshot_download = None


FASTER_WHISPER_MODEL_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
    "distil-large-v3": "Systran/faster-distil-whisper-large-v3",
}

DIRECTML_MODEL_REPOS = {
    "tiny": "openai/whisper-tiny",
    "base": "openai/whisper-base",
    "small": "openai/whisper-small",
    "medium": "openai/whisper-medium",
    "large-v3": "openai/whisper-large-v3",
    "distil-large-v3": "distil-whisper/distil-large-v3",
}

DIRECTML_ALLOWED_PATTERNS = (
    "*.json",
    "*.txt",
    "*.model",
    "*.safetensors",
)


class ModelDownloadService:
    def __init__(self, models_dir: Path) -> None:
        self._models_dir = models_dir

    def model_path(self, model_name: str, backend: str = "faster-whisper") -> Path:
        if backend == "directml":
            return self._models_dir / "directml" / model_name / "source"
        return self._models_dir / model_name

    def export_path(self, model_name: str, backend: str = "directml") -> Path:
        if backend != "directml":
            return self.model_path(model_name, backend=backend)
        return self._models_dir / "directml" / model_name / "onnx"

    def is_model_downloaded(self, model_name: str, backend: str = "faster-whisper") -> bool:
        model_path = self.model_path(model_name, backend=backend)
        if backend == "directml":
            markers = [model_path / "config.json", model_path / "tokenizer.json", model_path / "preprocessor_config.json"]
        else:
            markers = [model_path / "config.json", model_path / "tokenizer.json"]
        return model_path.exists() and any(marker.exists() for marker in markers)

    def is_export_prepared(self, model_name: str, backend: str = "directml") -> bool:
        if backend != "directml":
            return self.is_model_downloaded(model_name, backend=backend)
        export_path = self.export_path(model_name, backend=backend)
        return export_path.exists() and any(export_path.glob("*.onnx"))

    def ensure_model(self, model_name: str, backend: str = "faster-whisper") -> Path:
        if self.is_model_downloaded(model_name, backend=backend):
            return self.model_path(model_name, backend=backend)

        if snapshot_download is None:
            raise RuntimeError("huggingface_hub is not installed.")

        model_path = self.model_path(model_name, backend=backend)
        model_path.mkdir(parents=True, exist_ok=True)
        repo_id = self._repo_id(model_name, backend)
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(model_path),
            allow_patterns=self._allow_patterns(backend),
        )
        return model_path

    def _repo_id(self, model_name: str, backend: str) -> str:
        if backend == "directml":
            return DIRECTML_MODEL_REPOS.get(model_name, model_name)
        return FASTER_WHISPER_MODEL_REPOS.get(model_name, model_name)

    def _allow_patterns(self, backend: str) -> list[str] | None:
        if backend == "directml":
            return list(DIRECTML_ALLOWED_PATTERNS)
        return None