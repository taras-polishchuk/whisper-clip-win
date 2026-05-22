from app.services.model_download_service import ModelDownloadService


def test_directml_models_use_a_separate_source_path(tmp_path) -> None:
    service = ModelDownloadService(tmp_path)

    assert service.model_path("small", backend="directml") == tmp_path / "directml" / "small" / "source"
    assert service.export_path("small", backend="directml") == tmp_path / "directml" / "small" / "onnx"


def test_directml_export_prepared_requires_onnx_files(tmp_path) -> None:
    service = ModelDownloadService(tmp_path)
    export_path = service.export_path("small", backend="directml")
    export_path.mkdir(parents=True, exist_ok=True)

    assert service.is_export_prepared("small", backend="directml") is False

    (export_path / "encoder_model.onnx").write_text("stub", encoding="utf-8")

    assert service.is_export_prepared("small", backend="directml") is True