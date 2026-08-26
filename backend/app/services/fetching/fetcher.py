from dataclasses import dataclass
from time import sleep
from urllib.parse import urldefrag

import httpx

from app.services.fetching.rate_limit import DomainRateLimiter
from app.services.fetching.robots import RobotsPolicyChecker


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: str
    html: str
    content_type: str
    status_code: int


class WebFetchError(RuntimeError):
    pass


class HttpPageFetcher:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        user_agent: str,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
        max_bytes: int = 1_500_000,
        rate_limiter: DomainRateLimiter | None = None,
        robots_policy: RobotsPolicyChecker | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.max_bytes = max_bytes
        self.rate_limiter = rate_limiter
        self.robots_policy = robots_policy

    def fetch(self, url: str) -> FetchResult:
        clean_url = canonicalize_url(url)
        if self.robots_policy:
            decision = self.robots_policy.can_fetch(clean_url, self.user_agent)
            if not decision.allowed:
                raise WebFetchError(f"robots_disallowed:{decision.robots_url}")
        if self.rate_limiter:
            self.rate_limiter.wait(clean_url)

        headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml"}
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True, headers=headers) as client:
                    response = client.get(clean_url)
                    response.raise_for_status()
                break
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise
                sleep(self.retry_backoff_seconds * (attempt + 1))
        else:
            raise WebFetchError(str(last_error or "fetch_failed"))

        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            raise WebFetchError(f"unsupported_content_type:{content_type or 'unknown'}")
        content = response.content
        if len(content) > self.max_bytes:
            raise WebFetchError(f"response_too_large:{len(content)}")
        return FetchResult(
            url=clean_url,
            final_url=canonicalize_url(str(response.url)),
            html=response.text,
            content_type=content_type,
            status_code=response.status_code,
        )


def canonicalize_url(url: str) -> str:
    url_without_fragment, _fragment = urldefrag(url.strip())
    return url_without_fragment
