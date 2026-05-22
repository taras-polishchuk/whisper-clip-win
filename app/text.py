import re
from collections.abc import Iterable, Mapping


def normalize_text(text: str) -> str:
    compacted = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([,.;:!?])", r"\1", compacted)


def normalize_transcript(chunks: Iterable[str]) -> str:
    text = " ".join(chunk.strip() for chunk in chunks if chunk and chunk.strip())
    return normalize_text(text)


def build_runtime_prompt(initial_prompt: str, custom_terms: Iterable[str]) -> str:
    terms = [term.strip() for term in custom_terms if term and term.strip()]
    if not terms:
        return initial_prompt.strip()

    unique_terms = list(dict.fromkeys(terms))
    appendix = f"Обов'язково збережи написання термінів: {', '.join(unique_terms)}."
    base_prompt = initial_prompt.strip()
    return f"{base_prompt} {appendix}".strip()


def apply_replacement_rules(text: str, replacement_rules: Mapping[str, str]) -> str:
    normalized = text
    for source, target in replacement_rules.items():
        stripped_source = source.strip()
        stripped_target = target.strip()
        if not stripped_source or not stripped_target:
            continue

        pattern = re.compile(rf"(?<!\w){re.escape(stripped_source)}(?!\w)", re.IGNORECASE)
        normalized = pattern.sub(stripped_target, normalized)
    return normalized


def postprocess_transcript(chunks: Iterable[str], replacement_rules: Mapping[str, str]) -> str:
    text = normalize_transcript(chunks)
    if not text:
        return ""
    return normalize_text(apply_replacement_rules(text, replacement_rules))