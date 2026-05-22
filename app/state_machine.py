from __future__ import annotations

from app.models.app_state import AppEvent, AppState
from app.models.dto import Transition


class AppStateMachine:
    def __init__(self, initial_state: AppState = AppState.BOOTING) -> None:
        self._state = initial_state

    @property
    def state(self) -> AppState:
        return self._state

    def dispatch(self, event: AppEvent, payload: object | None = None) -> Transition:
        previous = self._state
        next_state = self._resolve_transition(previous, event)
        changed = next_state != previous
        if changed:
            self._state = next_state
        return Transition(previous, event, next_state, payload=payload, changed=changed)

    def _resolve_transition(self, state: AppState, event: AppEvent) -> AppState:
        if event == AppEvent.FAILURE:
            return AppState.ERROR

        if state == AppState.BOOTING and event == AppEvent.APP_STARTED:
            return AppState.CHECKING_ENV

        if state == AppState.CHECKING_ENV:
            if event == AppEvent.MODEL_MISSING:
                return AppState.DOWNLOADING_MODEL
            if event == AppEvent.ENV_OK:
                return AppState.LOADING_MODEL

        if state == AppState.DOWNLOADING_MODEL:
            if event in {AppEvent.MODEL_DOWNLOAD_COMPLETED, AppEvent.ENV_OK}:
                return AppState.LOADING_MODEL

        if state == AppState.LOADING_MODEL and event == AppEvent.MODEL_LOADED:
            return AppState.IDLE

        if state == AppState.IDLE and event == AppEvent.HOTKEY_PRESSED:
            return AppState.RECORDING

        if state == AppState.RECORDING and event == AppEvent.HOTKEY_PRESSED:
            return AppState.STOPPING_RECORDING

        if state == AppState.STOPPING_RECORDING and event == AppEvent.AUDIO_READY:
            return AppState.TRANSCRIBING

        if state == AppState.TRANSCRIBING:
            if event == AppEvent.TRANSCRIPTION_READY:
                return AppState.PASTING
            if event == AppEvent.TRANSCRIPTION_EMPTY:
                return AppState.IDLE

        if state == AppState.PASTING:
            if event == AppEvent.PASTE_SUCCEEDED:
                return AppState.IDLE
            if event == AppEvent.PASTE_SKIPPED:
                return AppState.CLIPBOARD_ONLY

        if state in {AppState.CLIPBOARD_ONLY, AppState.ERROR} and event == AppEvent.RESET:
            return AppState.IDLE

        return state