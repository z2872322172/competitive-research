import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedEvidence:
    quote: str
    char_start: int
    char_end: int
    quality_score: float
    language: str


STOPWORDS = {
    "about",
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "research",
    "competitive",
}


def extract_evidence(paragraphs: list[str], *, keywords: list[str], max_items: int = 3) -> list[ExtractedEvidence]:
    normalized_keywords = [item.lower() for item in keywords if len(item.strip()) >= 2]
    scored: list[tuple[float, int, str]] = []
    cursor = 0
    for paragraph in paragraphs:
        text = clamp_quote(paragraph)
        lowered = text.lower()
        keyword_hits = sum(1 for keyword in normalized_keywords if keyword in lowered)
        length_score = min(len(text) / 600, 1.0)
        score = min(0.35 + keyword_hits * 0.18 + length_score * 0.25, 0.95)
        if len(text) >= 80:
            scored.append((score, cursor, text))
        cursor += len(paragraph) + 2

    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        ExtractedEvidence(
            quote=text,
            char_start=start,
            char_end=start + len(text),
            quality_score=score,
            language=detect_language(text),
        )
        for score, start, text in scored[:max_items]
    ]


def build_keywords(prompt: str, scope: dict) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", prompt)
    scoped = []
    for key in ["competitors", "dimensions", "source_preferences"]:
        scoped.extend(str(item) for item in scope.get(key, []) if item)
    return list(dict.fromkeys([item for item in scoped + words if item.lower() not in STOPWORDS]))


def clamp_quote(text: str, max_chars: int = 900) -> str:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0].rstrip(".,;:") + "..."


def detect_language(text: str) -> str:
    cjk_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    return "zh" if cjk_chars >= max(3, len(text) // 12) else "en"
