# WhisperClip Windows MVP

Windows tray application for push-to-talk transcription with local `faster-whisper`, GPU inference, clipboard fallback, and focused-window autopaste.

## MVP capabilities

- Runs as a background Windows app without a console.
- Keeps a tray icon active and listens to a global hotkey.
- Starts and stops microphone recording with the same hotkey.
- Downloads the selected Whisper model on first launch.
- Loads the model once and keeps it resident in memory.
- Copies every transcript to the clipboard.
- Attempts `Ctrl+V` into the currently focused window when autopaste is enabled.
- Can register itself in the current user's Windows startup list.
- Exposes decode settings, custom vocabulary, and replacement rules in the settings window.
- Shows a minimal always-on-top overlay to indicate idle, recording, transcribing, and error states.

## Project layout

```text
whisper-clip-win/
  app/
    bootstrap.py
    config.py
    logging_setup.py
    state_machine.py
    text.py
    models/
    services/
    ui/
  tests/
  requirements.txt
  build.spec
  main.py
```

## Runtime requirements

- Windows 11 or Windows 10.
- Python 3.11.
- CPU mode works on a standard Windows machine.
- GPU acceleration now has two runtime paths:
  - NVIDIA + CUDA/cuDNN via `faster-whisper` and `ctranslate2`.
  - AMD / Intel / NVIDIA via Windows DirectML.

The app now supports three execution targets:

- `auto`: prefer NVIDIA/CUDA, otherwise use DirectML on Windows GPU hardware, otherwise fall back to CPU.
- `cpu`: always stay on the processor.
- `gpu`: require some GPU backend and choose CUDA first, then DirectML.

Internally the app now uses a multi-backend architecture:

- `faster-whisper` remains the CPU and CUDA backend.
- `DirectML` is the primary non-NVIDIA GPU path on Windows.

## Setup

1. Create and activate a Python virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. If you want CUDA on NVIDIA, verify `nvidia-smi` works in the same shell.
4. Run `python main.py`.
5. On first start, wait for the model download and initialization to finish.

On the first DirectML start, the app downloads the original Whisper checkpoint, exports it to ONNX, and stores the exported model under `%LOCALAPPDATA%/WhisperClip/models/directml` for later offline reuse.

## Configuration

The app stores configuration in `%APPDATA%/WhisperClip/config.json` and runtime assets in `%LOCALAPPDATA%/WhisperClip`.

Important defaults:

- Hotkey: `Ctrl+Alt+Space`
- Model: `small`
- Language: `uk`
- Device: `auto`
- Compute type: `auto`

Quality-related settings that can now be tuned without editing JSON manually:

- `beam_size`
- `temperature`
- `condition_on_previous_text`
- `vad_filter`
- `vad_min_silence_duration_ms`
- `initial_prompt`
- `custom_terms`
- `replacement_rules`

The settings window also shows detected graphics adapters and a runtime preview so users can see whether `auto` will choose CPU or GPU on their machine.

Current backend-specific notes:

- `compute_type` is used by the `faster-whisper` backend.
- DirectML manages precision internally, so the `compute_type` selector is informational there.
- `vad_filter` remains implemented only on the `faster-whisper` path.

Decode and post-processing settings apply immediately. Model or device changes still require an app restart.

## Packaging

This repository now ships a Windows release skeleton built around `PyInstaller` and `Inno Setup`.

Version and product metadata live in `app/release.py` and are reused by the runtime, `build.spec`, and the installer.

Recommended flow:

1. Update the version in `app/release.py`.
2. Optionally add `assets/icons/whisperclip.ico` to brand the EXE and installer.
3. Install Inno Setup 6 if you want a one-file installer.
4. Run the release script from Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_release.ps1
```

By default the script:

- builds an onedir application via `pyinstaller build.spec`
- emits `dist/WhisperClip/WhisperClip.exe`
- compiles `installer.iss` into `release/WhisperClip-Setup-<version>.exe`
- optionally signs the EXE and installer if signing environment variables are configured

Useful switches:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_release.ps1 -Clean
powershell -ExecutionPolicy Bypass -File .\build_release.ps1 -SkipInstaller
powershell -ExecutionPolicy Bypass -File .\build_release.ps1 -SkipSign
```

Optional signing environment variables:

- `SIGNTOOL_EXE` - explicit path to `signtool.exe`
- `WINDOWS_PFX_PATH` and `WINDOWS_PFX_PASSWORD` - sign using a PFX file
- `WINDOWS_CERT_THUMBPRINT` - sign using a cert already installed in the certificate store
- `WINDOWS_TIMESTAMP_URL` - RFC3161 timestamp URL, defaults to `http://timestamp.digicert.com`

The installer intentionally does not bundle Whisper models. End users install a small app first, then the selected model is downloaded on first launch into `%LOCALAPPDATA%\WhisperClip\models`.

Packaging `faster-whisper` on Windows with GPU support usually needs at least one iteration to verify bundled DLLs and CUDA runtime compatibility.
Packaging DirectML adds the ONNX Runtime and transformer stack, so verify the packaged build on the target GPU class you care about.

## Validation strategy

- `tests/test_state_machine.py` covers the explicit state transitions.
- `tests/test_config.py` covers config persistence.
- `tests/test_text.py` covers transcript normalization.
- `tests/test_runtime_preferences.py` covers backend routing.
- `tests/test_model_download_service.py` covers backend-specific model paths.
