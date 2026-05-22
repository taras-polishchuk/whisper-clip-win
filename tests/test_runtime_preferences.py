from app.runtime_preferences import GraphicsAdapter, resolve_runtime_preference


def test_auto_selects_gpu_when_nvidia_and_cuda_are_available() -> None:
    resolution = resolve_runtime_preference(
        "auto",
        "auto",
        [GraphicsAdapter(name="NVIDIA GeForce RTX 4070", vendor="NVIDIA")],
        cuda_available=True,
        directml_available=True,
    )

    assert resolution.actual_backend == "faster-whisper"
    assert resolution.actual_device == "cuda"
    assert resolution.actual_compute_type == "float16"
    assert resolution.accelerator_name == "NVIDIA GeForce RTX 4070"
    assert resolution.used_auto_fallback is False


def test_auto_selects_directml_for_amd_gpu_when_available() -> None:
    resolution = resolve_runtime_preference(
        "auto",
        "auto",
        [GraphicsAdapter(name="Radeon RX 580 Series", vendor="Advanced Micro Devices, Inc.")],
        cuda_available=False,
        directml_available=True,
    )

    assert resolution.actual_backend == "directml"
    assert resolution.actual_device == "directml"
    assert resolution.actual_compute_type == "managed"
    assert resolution.used_auto_fallback is False
    assert "DirectML" in resolution.summary
    assert "Radeon RX 580 Series" in resolution.summary


def test_auto_falls_back_to_cpu_when_no_gpu_backend_is_available() -> None:
    resolution = resolve_runtime_preference(
        "auto",
        "auto",
        [GraphicsAdapter(name="Radeon RX 580 Series", vendor="Advanced Micro Devices, Inc.")],
        cuda_available=False,
        directml_available=False,
    )

    assert resolution.actual_backend == "faster-whisper"
    assert resolution.actual_device == "cpu"
    assert resolution.actual_compute_type == "int8"
    assert resolution.used_auto_fallback is True


def test_gpu_mode_requires_some_supported_gpu_runtime() -> None:
    try:
        resolve_runtime_preference(
            "gpu",
            "auto",
            [GraphicsAdapter(name="Intel Iris Xe Graphics", vendor="Intel")],
            cuda_available=False,
            directml_available=False,
        )
    except RuntimeError as exc:
        assert "GPU mode was requested" in str(exc)
        assert "Intel Iris Xe Graphics" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected GPU mode without CUDA support to fail.")


def test_gpu_mode_uses_directml_when_cuda_is_unavailable() -> None:
    resolution = resolve_runtime_preference(
        "gpu",
        "auto",
        [GraphicsAdapter(name="Intel Iris Xe Graphics", vendor="Intel")],
        cuda_available=False,
        directml_available=True,
    )

    assert resolution.actual_backend == "directml"
    assert resolution.actual_device == "directml"
    assert resolution.actual_compute_type == "managed"


def test_cpu_mode_stays_on_cpu_even_when_nvidia_is_available() -> None:
    resolution = resolve_runtime_preference(
        "cpu",
        "auto",
        [GraphicsAdapter(name="NVIDIA GeForce RTX 4070", vendor="NVIDIA")],
        cuda_available=True,
        directml_available=True,
    )

    assert resolution.actual_backend == "faster-whisper"
    assert resolution.actual_device == "cpu"
    assert resolution.actual_compute_type == "int8"
    assert resolution.used_auto_fallback is False