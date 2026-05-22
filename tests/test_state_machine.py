from app.models.app_state import AppEvent, AppState
from app.state_machine import AppStateMachine


def test_happy_path_for_existing_model() -> None:
    machine = AppStateMachine()

    assert machine.dispatch(AppEvent.APP_STARTED).to_state == AppState.CHECKING_ENV
    assert machine.dispatch(AppEvent.ENV_OK).to_state == AppState.LOADING_MODEL
    assert machine.dispatch(AppEvent.MODEL_LOADED).to_state == AppState.IDLE
    assert machine.dispatch(AppEvent.HOTKEY_PRESSED).to_state == AppState.RECORDING
    assert machine.dispatch(AppEvent.HOTKEY_PRESSED).to_state == AppState.STOPPING_RECORDING
    assert machine.dispatch(AppEvent.AUDIO_READY).to_state == AppState.TRANSCRIBING
    assert machine.dispatch(AppEvent.TRANSCRIPTION_READY).to_state == AppState.PASTING
    assert machine.dispatch(AppEvent.PASTE_SUCCEEDED).to_state == AppState.IDLE


def test_download_path_then_clipboard_fallback() -> None:
    machine = AppStateMachine()

    machine.dispatch(AppEvent.APP_STARTED)
    assert machine.dispatch(AppEvent.MODEL_MISSING).to_state == AppState.DOWNLOADING_MODEL
    assert machine.dispatch(AppEvent.MODEL_DOWNLOAD_COMPLETED).to_state == AppState.LOADING_MODEL
    assert machine.dispatch(AppEvent.MODEL_LOADED).to_state == AppState.IDLE
    assert machine.dispatch(AppEvent.HOTKEY_PRESSED).to_state == AppState.RECORDING
    assert machine.dispatch(AppEvent.HOTKEY_PRESSED).to_state == AppState.STOPPING_RECORDING
    assert machine.dispatch(AppEvent.AUDIO_READY).to_state == AppState.TRANSCRIBING
    assert machine.dispatch(AppEvent.TRANSCRIPTION_READY).to_state == AppState.PASTING
    assert machine.dispatch(AppEvent.PASTE_SKIPPED).to_state == AppState.CLIPBOARD_ONLY
    assert machine.dispatch(AppEvent.RESET).to_state == AppState.IDLE


def test_loading_can_start_after_model_missing_without_download_completed() -> None:
    machine = AppStateMachine()

    machine.dispatch(AppEvent.APP_STARTED)
    assert machine.dispatch(AppEvent.MODEL_MISSING).to_state == AppState.DOWNLOADING_MODEL
    assert machine.dispatch(AppEvent.ENV_OK).to_state == AppState.LOADING_MODEL
    assert machine.dispatch(AppEvent.MODEL_LOADED).to_state == AppState.IDLE


def test_busy_state_ignores_new_record_request() -> None:
    machine = AppStateMachine()

    machine.dispatch(AppEvent.APP_STARTED)
    machine.dispatch(AppEvent.ENV_OK)
    machine.dispatch(AppEvent.MODEL_LOADED)
    machine.dispatch(AppEvent.HOTKEY_PRESSED)
    machine.dispatch(AppEvent.HOTKEY_PRESSED)
    machine.dispatch(AppEvent.AUDIO_READY)

    transition = machine.dispatch(AppEvent.HOTKEY_PRESSED)
    assert transition.changed is False
    assert transition.to_state == AppState.TRANSCRIBING