from urllib.parse import urlparse

from app.config import Settings
from app.services.search.adapters import classify_source_type
from app.services.search.base import SearchResult
from app.services.social.base import SocialListeningAdapter

PUBLIC_SOCIAL_PLATFORMS = {
    "reddit.com": "reddit",
    "news.ycombinator.com": "hacker_news",
    "producthunt.com": "product_hunt",
    "x.com": "x",
    "twitter.com": "x",
    "weibo.com": "weibo",
    "zhihu.com": "zhihu",
}


class PublicSocialUrlAdapter:
    def __init__(self, urls: list[str]) -> None:
        self.urls = list(dict.fromkeys(urls))

    def search(self, query: str, *, max_results: int) -> list[SearchResult]:
        return [
            SearchResult(
                title=urlparse(url).netloc or url,
                url=url,
                snippet="Public social URL supplied in the research task.",
                score=0.6,
                source_type="social",
                metadata=build_public_social_metadata(url),
            )
            for url in self.urls[:max_results]
        ]


class NullSocialListeningAdapter:
    def search(self, query: str, *, max_results: int) -> list[SearchResult]:
        return []


def split_social_urls(urls: list[str]) -> tuple[list[str], list[str]]:
    manual_urls: list[str] = []
    social_urls: list[str] = []
    for url in dict.fromkeys(urls):
        if classify_source_type(url) == "social":
            social_urls.append(url)
        else:
            manual_urls.append(url)
    return manual_urls, social_urls


def build_social_listening_adapter(settings: Settings, *, social_urls: list[str]) -> SocialListeningAdapter:
    if social_urls:
        return PublicSocialUrlAdapter(social_urls)
    return NullSocialListeningAdapter()


def build_public_social_metadata(url: str) -> dict:
    platform = detect_public_social_platform(url)
    return {
        "platform": platform,
        "social_fields": {
            "sentiment": "unknown",
            "heat": None,
            "published_at": None,
            "interaction_metrics": {},
        },
    }


def detect_public_social_platform(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.").removeprefix("old.").removeprefix("mobile.")
    for platform_host, platform_name in PUBLIC_SOCIAL_PLATFORMS.items():
        if host == platform_host or host.endswith(f".{platform_host}"):
            return platform_name
    return "public_social"
