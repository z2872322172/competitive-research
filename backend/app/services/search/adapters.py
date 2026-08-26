import re
from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.services.search.base import SearchAdapter, SearchProviderUnavailable, SearchResult


URL_PATTERN = re.compile(r"https?://[^\s,，)）\]>\"']+")

SOCIAL_HOSTS = {
    "reddit.com",
    "www.reddit.com",
    "old.reddit.com",
    "x.com",
    "twitter.com",
    "mobile.twitter.com",
    "weibo.com",
    "www.weibo.com",
    "zhihu.com",
    "www.zhihu.com",
    "news.ycombinator.com",
    "producthunt.com",
    "www.producthunt.com",
    "threads.net",
    "www.threads.net",
}


class TavilySearchAdapter:
    endpoint = "https://api.tavily.com/search"

    def __init__(self, api_key: str, *, timeout_seconds: float = 12.0) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, *, max_results: int) -> list[SearchResult]:
        payload = {
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": False,
            "include_images": False,
            "include_raw_content": False,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(self.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()

        results: list[SearchResult] = []
        for item in body.get("results", []):
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            results.append(
                SearchResult(
                    title=str(item.get("title") or url),
                    url=url,
                    snippet=str(item.get("content") or ""),
                    score=float(item.get("score") or 0.5),
                    source_type=classify_source_type(url),
                )
            )
        return results


class ManualUrlAdapter:
    def __init__(self, urls: list[str]) -> None:
        self.urls = list(dict.fromkeys(urls))

    def search(self, query: str, *, max_results: int) -> list[SearchResult]:
        return [
            SearchResult(
                title=urlparse(url).netloc or url,
                url=url,
                snippet="Manual URL supplied in the research task.",
                score=0.7,
                source_type=classify_source_type(url),
            )
            for url in self.urls[:max_results]
        ]


class NullSearchAdapter:
    def search(self, query: str, *, max_results: int) -> list[SearchResult]:
        return []


def build_search_adapter(settings: Settings, *, manual_urls: list[str]) -> SearchAdapter:
    if settings.search_provider == "tavily" and settings.tavily_api_key:
        return TavilySearchAdapter(settings.tavily_api_key, timeout_seconds=settings.fetch_timeout_seconds)
    if manual_urls:
        return ManualUrlAdapter(manual_urls)
    if settings.search_provider == "tavily":
        raise SearchProviderUnavailable("tavily_api_key_missing")
    return NullSearchAdapter()


def extract_urls(*values: str | list[str] | None) -> list[str]:
    urls: list[str] = []
    for value in values:
        if value is None:
            continue
        text = " ".join(value) if isinstance(value, list) else value
        urls.extend(match.rstrip(".,;。；") for match in URL_PATTERN.findall(text))
    return list(dict.fromkeys(urls))


def classify_source_type(url: str) -> str:
    host = urlparse(url).netloc.lower()
    path = urlparse(url).path.lower()
    if host in SOCIAL_HOSTS or any(host.endswith(f".{social_host}") for social_host in SOCIAL_HOSTS):
        return "social"
    if "docs." in host or "/docs" in path or "help." in host:
        return "docs"
    if "pricing" in path or "price" in path:
        return "official"
    if any(token in host for token in ["news", "blog", "medium", "substack"]):
        return "news"
    return "web"
