from pathlib import Path

from app.config import AppConfig


def test_config_round_trip(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config = AppConfig(
        hotkey="Ctrl+Shift+Space",
        model_name="medium",
        device="auto",
        compute_type="auto",
        beam_size=7,
        temperature=0.2,
        condition_on_previous_text=False,
        vad_filter=True,
        vad_min_silence_duration_ms=800,
        custom_terms=["WhisperClip", "TypeScript", "PostgreSQL"],
        replacement_rules={"візпер": "Whisper", "реакт": "React"},
        config_file=config_path,
        models_dir=tmp_path / "models",
        temp_dir=tmp_path / "tmp",
        log_dir=tmp_path / "logs",
    )

    config.save()
    loaded = AppConfig.load(config_path)

    assert loaded.hotkey == "Ctrl+Shift+Space"
    assert loaded.model_name == "medium"
    assert loaded.device == "auto"
    assert loaded.compute_type == "auto"
    assert loaded.beam_size == 7
    assert loaded.temperature == 0.2
    assert loaded.condition_on_previous_text is False
    assert loaded.vad_filter is True
    assert loaded.vad_min_silence_duration_ms == 800
    assert loaded.custom_terms == ["WhisperClip", "TypeScript", "PostgreSQL"]
    assert loaded.replacement_rules == {"візпер": "Whisper", "реакт": "React"}
    assert loaded.models_dir == tmp_path / "models"
    assert loaded.temp_dir == tmp_path / "tmp"
    assert loaded.log_dir == tmp_path / "logs"