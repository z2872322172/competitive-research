from typing import Protocol

from app.services.search.base import SearchResult


class SocialListeningAdapter(Protocol):
    def search(self, query: str, *, max_results: int) -> list[SearchResult]:
        """Return normalized public social discussion candidates."""
