from time import monotonic, sleep
from urllib.parse import urlparse


class DomainRateLimiter:
    def __init__(self, *, min_interval_seconds: float) -> None:
        self.min_interval_seconds = min_interval_seconds
        self._last_request_at: dict[str, float] = {}

    def wait(self, url: str) -> None:
        if self.min_interval_seconds <= 0:
            return
        domain = urlparse(url).netloc.lower()
        if not domain:
            return
        now = monotonic()
        last_request_at = self._last_request_at.get(domain)
        if last_request_at is not None:
            remaining = self.min_interval_seconds - (now - last_request_at)
            if remaining > 0:
                sleep(remaining)
        self._last_request_at[domain] = monotonic()
