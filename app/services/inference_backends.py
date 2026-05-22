from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import logging
import warnings
import wave

import numpy as np

from app.runtime_preferences import RuntimeResolution
from app.services.model_download_service import ModelDownloadService

try:
    from faster_whisper import WhisperModel
except ImportError:  # pragma: no cover - optional at import time
    WhisperModel = None

try:
    from optimum.onnxruntime import ORTModelForSpeechSeq2Seq
    from transformers import AutoProcessor
except (ImportError, OSError):  # pragma: no cover - optional at import time
    ORTModelForSpeechSeq2Seq = None
    AutoProcessor = None

try:
    import onnxruntime as ort
except (ImportError, OSError):  # pragma: no cover - optional at import time
    ort = None

try:
    from torch.jit import TracerWarning
except ImportError:  # pragma: no cover - optional at import time
    TracerWarning = Warning


DIRECTML_PROVIDER = "DmlExecutionProvider"
TRANSFORMERS_NOISE_LOGGERS = (
    "optimum.exporters.onnx.convert",
    "optimum.onnxruntime.modeling_decoder",
    "optimum.onnxruntime.modeling_seq2seq",
    "transformers.configuration_utils",
    "transformers.generation.configuration_utils",
    "transformers.generation.utils",
    "transformers.integrations.tensor_parallel",
    "transformers.modeling_utils",
)


@dataclass(slots=True, frozen=True)
class TranscriptionSegment:
    text: str


@dataclass(slots=True, frozen=True)
class TranscriptionInfo:
    language: str


class LoadedTranscriptionModel(Protocol):
    def transcribe(self, audio_path: str, **kwargs: Any) -> tuple[list[TranscriptionSegment], TranscriptionInfo]:
        ...


class FasterWhisperBackend:
    def __init__(self, model_path: Path, device: str, compute_type: str) -> None:
        if WhisperModel is None:
            raise RuntimeError("faster-whisper is not installed.")
        self._model = WhisperModel(
            str(model_path),
            device=device,
            compute_type=compute_type,
            local_files_only=True,
        )

    def transcribe(self, audio_path: str, **kwargs: Any):
        return self._model.transcribe(audio_path, **kwargs)


class DirectMLBackend:
    def __init__(self, source_path: Path, export_path: Path) -> None:
        if ORTModelForSpeechSeq2Seq is None or AutoProcessor is None or ort is None:
            raise RuntimeError(
                "DirectML backend dependencies are not installed. Install onnxruntime-directml, optimum-onnx, "
                "transformers, and sentencepiece."
            )

        self._configure_runtime_logging()
        self._model, self._processor = self._load_or_export_model(source_path, export_path)

    def transcribe(self, audio_path: str, **kwargs: Any) -> tuple[list[TranscriptionSegment], TranscriptionInfo]:
        language = str(kwargs.get("language") or "uk")
        audio_input = self._load_audio_input(audio_path)
        features = self._processor.feature_extractor(
            audio_input["array"],
            sampling_rate=audio_input["sampling_rate"],
            return_tensors="pt",
            return_attention_mask=True,
        )

        generate_kwargs: dict[str, Any] = {
            "input_features": features.input_features,
            "attention_mask": getattr(features, "attention_mask", None),
            "task": "transcribe",
            "language": language,
            "num_beams": int(kwargs.get("beam_size", 5)),
            "temperature": float(kwargs.get("temperature", 0.0)),
            "condition_on_prev_tokens": bool(kwargs.get("condition_on_previous_text", True)),
            "return_timestamps": False,
            "return_segments": True,
        }

        initial_prompt = str(kwargs.get("initial_prompt") or "").strip()
        if initial_prompt:
            generate_kwargs["prompt_ids"] = self._processor.get_prompt_ids(
                initial_prompt,
                return_tensors="pt",
            )

        generated = self._model.generate(**generate_kwargs)
        segments = self._decode_segments(generated)
        if not segments:
            text = self._decode_sequences(generated)
            segments = [TranscriptionSegment(text=text)] if text else []
        info = TranscriptionInfo(language=language)
        return segments, info

    def _decode_segments(self, generated: Any) -> list[TranscriptionSegment]:
        if not isinstance(generated, dict):
            return []
        raw_segments = generated.get("segments") or []
        decoded_segments: list[TranscriptionSegment] = []
        for item in raw_segments:
            tokens = item.get("tokens") if isinstance(item, dict) else None
            text = self._decode_tokens(tokens)
            if text:
                decoded_segments.append(TranscriptionSegment(text=text))
        return decoded_segments

    def _decode_sequences(self, generated: Any) -> str:
        if isinstance(generated, dict):
            sequences = generated.get("sequences")
        else:
            sequences = generated
        return self._decode_tokens(sequences)

    def _decode_tokens(self, tokens: Any) -> str:
        if tokens is None:
            return ""
        if hasattr(tokens, "ndim") and getattr(tokens, "ndim") == 1 and hasattr(tokens, "unsqueeze"):
            batch_tokens = tokens.unsqueeze(0)
        else:
            batch_tokens = tokens
        decoded = self._processor.batch_decode(batch_tokens, skip_special_tokens=True)
        if not decoded:
            return ""
        return str(decoded[0]).strip()

    def _load_or_export_model(
        self,
        source_path: Path,
        export_path: Path,
    ):
        export_path.mkdir(parents=True, exist_ok=True)

        if any(export_path.glob("*.onnx")):
            processor = AutoProcessor.from_pretrained(str(export_path), local_files_only=True)
            with self._suppress_export_warnings():
                model = ORTModelForSpeechSeq2Seq.from_pretrained(
                    str(export_path),
                    provider=DIRECTML_PROVIDER,
                    local_files_only=True,
                    session_options=self._build_session_options(),
                    use_io_binding=False,
                    use_merged=False,
                )
            self._prime_generation_config(model)
            return model, processor

        processor = AutoProcessor.from_pretrained(str(source_path), local_files_only=True)
        with self._suppress_export_warnings():
            model = ORTModelForSpeechSeq2Seq.from_pretrained(
                str(source_path),
                export=True,
                provider=DIRECTML_PROVIDER,
                local_files_only=True,
                session_options=self._build_session_options(),
                use_io_binding=False,
                use_merged=False,
            )
        model.save_pretrained(str(export_path))
        processor.save_pretrained(str(export_path))
        reloaded_processor = AutoProcessor.from_pretrained(str(export_path), local_files_only=True)
        with self._suppress_export_warnings():
            reloaded_model = ORTModelForSpeechSeq2Seq.from_pretrained(
                str(export_path),
                provider=DIRECTML_PROVIDER,
                local_files_only=True,
                session_options=self._build_session_options(),
                use_io_binding=False,
                use_merged=False,
            )
        self._prime_generation_config(reloaded_model)
        return reloaded_model, reloaded_processor

    def _load_audio_input(self, audio_path: str) -> dict[str, Any]:
        with wave.open(audio_path, "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            frame_data = wav_file.readframes(wav_file.getnframes())

        if sample_width != 2:
            raise RuntimeError("DirectML backend currently expects 16-bit PCM WAV input.")

        waveform = np.frombuffer(frame_data, dtype=np.int16).astype(np.float32) / 32768.0
        if channels > 1:
            waveform = waveform.reshape(-1, channels).mean(axis=1)

        return {
            "array": waveform,
            "sampling_rate": sample_rate,
        }

    def _configure_runtime_logging(self) -> None:
        ort.set_default_logger_severity(3)
        for logger_name in TRANSFORMERS_NOISE_LOGGERS:
            logging.getLogger(logger_name).setLevel(logging.ERROR)

    def _build_session_options(self):
        session_options = ort.SessionOptions()
        session_options.log_severity_level = 3
        session_options.log_verbosity_level = 0
        return session_options

    @contextmanager
    def _suppress_export_warnings(self):
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=TracerWarning)
            yield

    def _prime_generation_config(self, model: Any) -> None:
        generation_config = getattr(model, "generation_config", None)
        model_config = getattr(model, "config", None)
        if generation_config is None or model_config is None:
            return
        suppress_tokens = getattr(model_config, "suppress_tokens", None)
        begin_suppress_tokens = getattr(model_config, "begin_suppress_tokens", None)
        if suppress_tokens is not None:
            generation_config.suppress_tokens = list(suppress_tokens)
        if begin_suppress_tokens is not None:
            generation_config.begin_suppress_tokens = list(begin_suppress_tokens)


def load_transcription_backend(
    model_name: str,
    runtime_resolution: RuntimeResolution,
    downloader: ModelDownloadService,
) -> LoadedTranscriptionModel:
    if runtime_resolution.actual_backend == "directml":
        source_path = downloader.model_path(model_name, backend="directml")
        export_path = downloader.export_path(model_name, backend="directml")
        return DirectMLBackend(source_path, export_path)

    model_path = downloader.model_path(model_name, backend="faster-whisper")
    return FasterWhisperBackend(
        model_path=model_path,
        device=runtime_resolution.actual_device,
        compute_type=runtime_resolution.actual_compute_type,
    )