from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from app.release import APP_DISPLAY_NAME
from app.runtime_preferences import normalize_compute_type, normalize_device_preference


DEFAULT_INITIAL_PROMPT = (
    "Транскрипція українською мовою. Технічні назви та терміни пишуться "
    "англійською: Python, JavaScript, TypeScript, React, Node.js, Docker, "
    "Kubernetes, Linux, Windows, macOS, Git, GitHub, API, REST, HTTP, HTTPS, "
    "JSON, SQL, NoSQL, MongoDB, PostgreSQL, Redis, AWS, GCP, Azure, CI/CD, "
    "CPU, GPU, RAM, SSD, USB, HTML, CSS, VS Code, Vim, bash, pip, npm, yarn, "
    "IntersectionObserver."
)


def _env_path(env_name: str, fallback: Path) -> Path:
    value = os.getenv(env_name)
    return Path(value) if value else fallback


def default_config_dir() -> Path:
    return _env_path("APPDATA", Path.home() / ".config") / "WhisperClip"


def default_local_dir() -> Path:
    return _env_path("LOCALAPPDATA", Path.home() / ".local" / "share") / "WhisperClip"


def default_config_path() -> Path:
    return default_config_dir() / "config.json"


def default_models_dir() -> Path:
    return default_local_dir() / "models"


def default_temp_dir() -> Path:
    return default_local_dir() / "tmp"


def default_log_dir() -> Path:
    return default_local_dir() / "logs"


@dataclass(slots=True)
class AppConfig:
    config_version: int = 1
    app_name: str = APP_DISPLAY_NAME
    hotkey: str = "Ctrl+Alt+Space"
    sample_rate: int = 16000
    channels: int = 1
    model_name: str = "small"
    language: str = "uk"
    device: str = "auto"
    compute_type: str = "auto"
    beam_size: int = 5
    temperature: float = 0.0
    condition_on_previous_text: bool = True
    vad_filter: bool = False
    vad_min_silence_duration_ms: int = 500
    overlay_enabled: bool = True
    autopaste_enabled: bool = True
    start_on_login: bool = False
    microphone_device: str | None = None
    initial_prompt: str = DEFAULT_INITIAL_PROMPT
    custom_terms: list[str] = field(default_factory=list)
    replacement_rules: dict[str, str] = field(default_factory=dict)
    config_file: Path = field(default_factory=default_config_path)
    models_dir: Path = field(default_factory=default_models_dir)
    temp_dir: Path = field(default_factory=default_temp_dir)
    log_dir: Path = field(default_factory=default_log_dir)

    @classmethod
    def load(cls, path: Path | None = None) -> "AppConfig":
        config_path = Path(path) if path else default_config_path()
        if not config_path.exists():
            return cls(config_file=config_path)

        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
        return cls(
            config_version=int(data.get("config_version", 1)),
            app_name=data.get("app_name", APP_DISPLAY_NAME),
            hotkey=data.get("hotkey", "Ctrl+Alt+Space"),
            sample_rate=int(data.get("sample_rate", 16000)),
            channels=int(data.get("channels", 1)),
            model_name=data.get("model_name", "small"),
            language=data.get("language", "uk"),
            device=normalize_device_preference(data.get("device", "auto")),
            compute_type=normalize_compute_type(data.get("compute_type", "auto")),
            beam_size=int(data.get("beam_size", 5)),
            temperature=float(data.get("temperature", 0.0)),
            condition_on_previous_text=bool(data.get("condition_on_previous_text", True)),
            vad_filter=bool(data.get("vad_filter", False)),
            vad_min_silence_duration_ms=int(data.get("vad_min_silence_duration_ms", 500)),
            overlay_enabled=bool(data.get("overlay_enabled", True)),
            autopaste_enabled=bool(data.get("autopaste_enabled", True)),
            start_on_login=bool(data.get("start_on_login", False)),
            microphone_device=data.get("microphone_device"),
            initial_prompt=data.get("initial_prompt", DEFAULT_INITIAL_PROMPT),
            custom_terms=[str(item).strip() for item in data.get("custom_terms", []) if str(item).strip()],
            replacement_rules={
                str(source).strip(): str(target).strip()
                for source, target in data.get("replacement_rules", {}).items()
                if str(source).strip() and str(target).strip()
            },
            config_file=config_path,
            models_dir=Path(data.get("models_dir", default_models_dir())),
            temp_dir=Path(data.get("temp_dir", default_temp_dir())),
            log_dir=Path(data.get("log_dir", default_log_dir())),
        )

    def ensure_runtime_dirs(self) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        self.ensure_runtime_dirs()
        payload = asdict(self)
        payload["config_file"] = str(self.config_file)
        payload["models_dir"] = str(self.models_dir)
        payload["temp_dir"] = str(self.temp_dir)
        payload["log_dir"] = str(self.log_dir)
        self.config_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def updated(self, **changes: Any) -> "AppConfig":
        return replace(self, **changes)

