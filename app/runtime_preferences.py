from __future__ import annotations

import json
import os
import shutil
import subprocess
from importlib import import_module
from collections.abc import Sequence
from dataclasses import dataclass


DEVICE_CHOICES = ("auto", "cpu", "gpu")
COMPUTE_TYPE_CHOICES = ("auto", "int8", "int8_float16", "float16", "float32")
BACKEND_CHOICES = ("faster-whisper", "directml")


@dataclass(slots=True, frozen=True)
class GraphicsAdapter:
    name: str
    vendor: str = ""

    @property
    def is_nvidia(self) -> bool:
        haystack = f"{self.name} {self.vendor}".lower()
        return "nvidia" in haystack

    @property
    def is_basic_display(self) -> bool:
        haystack = f"{self.name} {self.vendor}".lower()
        return "microsoft basic display" in haystack

    @property
    def label(self) -> str:
        if not self.vendor or self.vendor.lower() in self.name.lower():
            return self.name
        return f"{self.name} ({self.vendor})"


@dataclass(slots=True, frozen=True)
class RuntimeResolution:
    requested_device: str
    actual_device: str
    actual_backend: str
    requested_compute_type: str
    actual_compute_type: str
    accelerator_name: str | None
    detected_adapters: tuple[GraphicsAdapter, ...]
    used_auto_fallback: bool
    summary: str


def normalize_device_preference(value: str | None) -> str:
    raw_value = (value or "auto").strip().lower()
    legacy_map = {
        "cuda": "gpu",
        "cpu": "cpu",
        "gpu": "gpu",
        "auto": "auto",
    }
    normalized = legacy_map.get(raw_value, raw_value)
    return normalized if normalized in DEVICE_CHOICES else "auto"


def normalize_compute_type(value: str | None) -> str:
    normalized = (value or "auto").strip().lower()
    return normalized if normalized in COMPUTE_TYPE_CHOICES else "auto"


def detect_graphics_adapters() -> list[GraphicsAdapter]:
    if os.name != "nt":
        return []

    command = (
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name, AdapterCompatibility | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    if result.returncode != 0 or not result.stdout.strip():
        return []

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    if isinstance(payload, dict):
        payload = [payload]

    adapters: list[GraphicsAdapter] = []
    for item in payload:
        name = str(item.get("Name", "")).strip()
        vendor = str(item.get("AdapterCompatibility", "")).strip()
        if not name:
            continue
        adapter = GraphicsAdapter(name=name, vendor=vendor)
        if adapter.is_basic_display:
            continue
        adapters.append(adapter)
    return adapters


def cuda_runtime_available() -> bool:
    return os.name == "nt" and shutil.which("nvidia-smi") is not None


def _module_attribute_available(module_name: str, attribute_name: str) -> bool:
    try:
        module = import_module(module_name)
        getattr(module, attribute_name)
    except Exception:  # pragma: no cover - import/runtime dependent
        return False
    return True


def directml_runtime_available() -> bool:
    if os.name != "nt":
        return False
    if not _module_attribute_available("optimum.onnxruntime", "ORTModelForSpeechSeq2Seq"):
        return False
    if not _module_attribute_available("transformers", "AutoProcessor"):
        return False
    try:
        onnxruntime = import_module("onnxruntime")
        providers = onnxruntime.get_available_providers()
    except Exception:  # pragma: no cover - import/runtime dependent
        return False
    return "DmlExecutionProvider" in providers


def describe_graphics_adapters(adapters: Sequence[GraphicsAdapter]) -> str:
    visible_adapters = [adapter.label for adapter in adapters if not adapter.is_basic_display]
    if not visible_adapters:
        return "No dedicated graphics adapters detected."
    return ", ".join(visible_adapters)


def _preferred_directml_adapter(adapters: Sequence[GraphicsAdapter]) -> GraphicsAdapter | None:
    non_nvidia_adapter = next((adapter for adapter in adapters if not adapter.is_nvidia), None)
    if non_nvidia_adapter is not None:
        return non_nvidia_adapter
    return next(iter(adapters), None)


def resolve_runtime_preference(
    device_preference: str,
    compute_type_preference: str,
    adapters: Sequence[GraphicsAdapter],
    cuda_available: bool,
    directml_available: bool,
) -> RuntimeResolution:
    requested_device = normalize_device_preference(device_preference)
    requested_compute_type = normalize_compute_type(compute_type_preference)
    detected_adapters = tuple(adapter for adapter in adapters if not adapter.is_basic_display)
    detected_label = describe_graphics_adapters(detected_adapters)
    nvidia_adapter = next((adapter for adapter in detected_adapters if adapter.is_nvidia), None)
    directml_adapter = _preferred_directml_adapter(detected_adapters) if directml_available else None

    if requested_device == "gpu":
        if cuda_available and nvidia_adapter:
            actual_device = "cuda"
            actual_backend = "faster-whisper"
            accelerator_name = nvidia_adapter.name
            used_auto_fallback = False
            summary = f"Running on GPU with faster-whisper/CUDA: {nvidia_adapter.name}."
        elif directml_adapter is not None:
            actual_device = "directml"
            actual_backend = "directml"
            accelerator_name = directml_adapter.name
            used_auto_fallback = False
            summary = f"Running on GPU with DirectML: {directml_adapter.name}."
        else:
            raise RuntimeError(
                "GPU mode was requested, but no CUDA-compatible NVIDIA or DirectML runtime was detected. "
                f"Detected adapters: {detected_label}"
            )
    elif requested_device == "auto":
        if cuda_available and nvidia_adapter:
            actual_device = "cuda"
            actual_backend = "faster-whisper"
            accelerator_name = nvidia_adapter.name
            used_auto_fallback = False
            summary = f"Auto selected GPU via faster-whisper/CUDA: {nvidia_adapter.name}."
        elif directml_adapter is not None:
            actual_device = "directml"
            actual_backend = "directml"
            accelerator_name = directml_adapter.name
            used_auto_fallback = False
            summary = f"Auto selected GPU via DirectML: {directml_adapter.name}."
        else:
            actual_device = "cpu"
            actual_backend = "faster-whisper"
            accelerator_name = None
            used_auto_fallback = True
            if detected_adapters:
                summary = (
                    "Auto selected CPU. No compatible GPU backend is ready for the detected adapters: "
                    f"{detected_label}."
                )
            else:
                summary = "Auto selected CPU. No compatible GPU runtime was detected."
    else:
        actual_device = "cpu"
        actual_backend = "faster-whisper"
        accelerator_name = None
        used_auto_fallback = False
        if detected_adapters:
            summary = f"Running on CPU by user choice. Detected adapters: {detected_label}."
        else:
            summary = "Running on CPU by user choice."

    if actual_backend == "directml":
        actual_compute_type = "managed"
        summary = f"{summary} Precision is managed by the DirectML backend."
    else:
        actual_compute_type = requested_compute_type
        if actual_compute_type == "auto":
            actual_compute_type = "float16" if actual_device == "cuda" else "int8"
        summary = f"{summary} Compute type: {actual_compute_type}."

    return RuntimeResolution(
        requested_device=requested_device,
        actual_device=actual_device,
        actual_backend=actual_backend,
        requested_compute_type=requested_compute_type,
        actual_compute_type=actual_compute_type,
        accelerator_name=accelerator_name,
        detected_adapters=detected_adapters,
        used_auto_fallback=used_auto_fallback,
        summary=summary,
    )