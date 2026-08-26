from dataclasses import dataclass
from html.parser import HTMLParser
from importlib import import_module
from typing import Callable


@dataclass(frozen=True)
class ParsedPage:
    title: str
    text: str
    paragraphs: list[str]
    parser_name: str


class _ReadableHTMLParser(HTMLParser):
    block_tags = {"p", "li", "h1", "h2", "h3", "article", "section"}
    ignored_tags = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._ignored_depth = 0
        self._current: list[str] = []
        self.paragraphs: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        if tag in self.ignored_tags:
            self._ignored_depth += 1
        if tag in self.block_tags:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in self.ignored_tags and self._ignored_depth:
            self._ignored_depth -= 1
        if tag in self.block_tags:
            self._flush()

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self.title = f"{self.title} {text}".strip()
            return
        if self._ignored_depth:
            return
        self._current.append(text)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        text = " ".join(self._current).strip()
        self._current = []
        if len(text) >= 40:
            self.paragraphs.append(text)


def parse_html(html: str, *, prefer_trafilatura: bool = True) -> ParsedPage:
    fallback = parse_html_with_stdlib(html)
    if not prefer_trafilatura:
        return fallback

    trafilatura_page = parse_html_with_trafilatura(html, fallback_title=fallback.title)
    return trafilatura_page or fallback


def parse_html_with_stdlib(html: str) -> ParsedPage:
    parser = _ReadableHTMLParser()
    parser.feed(html)
    parser.close()
    paragraphs = dedupe_preserve_order(parser.paragraphs)
    return ParsedPage(title=parser.title, text="\n\n".join(paragraphs), paragraphs=paragraphs, parser_name="stdlib_html_parser")


def parse_html_with_trafilatura(html: str, *, fallback_title: str = "") -> ParsedPage | None:
    extract = load_trafilatura_extract()
    if extract is None:
        return None
    try:
        text = extract(html, include_comments=False, include_tables=False, favor_precision=True)
    except (TypeError, ValueError, RuntimeError):
        return None
    if not text:
        return None
    paragraphs = dedupe_preserve_order([item.strip() for item in text.splitlines() if len(item.strip()) >= 40])
    if not paragraphs:
        return None
    return ParsedPage(title=fallback_title, text="\n\n".join(paragraphs), paragraphs=paragraphs, parser_name="trafilatura")


def load_trafilatura_extract() -> Callable[..., str | None] | None:
    try:
        module = import_module("trafilatura")
    except ImportError:
        return None
    extract = getattr(module, "extract", None)
    return extract if callable(extract) else None


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
