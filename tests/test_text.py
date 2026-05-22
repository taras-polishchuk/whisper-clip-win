from app.text import apply_replacement_rules, build_runtime_prompt, normalize_transcript, postprocess_transcript


def test_normalize_transcript_compacts_whitespace() -> None:
    assert normalize_transcript([" Привіт", "", "   світе  ", " ! ", "Python  "]) == "Привіт світе! Python"


def test_build_runtime_prompt_appends_terms_without_duplicates() -> None:
    prompt = build_runtime_prompt("Базовий prompt.", ["WhisperClip", "React", "WhisperClip"])
    assert prompt == "Базовий prompt. Обов'язково збережи написання термінів: WhisperClip, React."


def test_apply_replacement_rules_is_case_insensitive() -> None:
    assert apply_replacement_rules("Візпер і реакт працюють.", {"візпер": "Whisper", "реакт": "React"}) == "Whisper і React працюють."


def test_postprocess_transcript_applies_replacements_after_normalization() -> None:
    text = postprocess_transcript(["  візпер  ", " і  ", "  реакт  "], {"візпер": "Whisper", "реакт": "React"})
    assert text == "Whisper і React"