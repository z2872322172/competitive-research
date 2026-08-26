from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx


@dataclass(frozen=True)
class RobotsDecision:
    allowed: bool
    robots_url: str
    reason: str = ""


class RobotsPolicyChecker:
    def __init__(self, *, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        self._cache: dict[str, RobotFileParser | None] = {}

    def can_fetch(self, url: str, user_agent: str) -> RobotsDecision:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = urljoin(origin, "/robots.txt")
        parser = self._cache.get(origin)
        if origin not in self._cache:
            parser = self._load_parser(robots_url)
            self._cache[origin] = parser
        if parser is None:
            return RobotsDecision(allowed=True, robots_url=robots_url, reason="robots_unavailable")
        return RobotsDecision(allowed=parser.can_fetch(user_agent, url), robots_url=robots_url)

    def _load_parser(self, robots_url: str) -> RobotFileParser | None:
        parser = RobotFileParser()
        parser.set_url(robots_url)
        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = client.get(robots_url)
            if response.status_code >= 400:
                return None
            parser.parse(response.text.splitlines())
            return parser
        except httpx.HTTPError:
            return None
