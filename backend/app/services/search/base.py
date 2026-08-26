from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    score: float = 0.5
    source_type: str = "web"
    metadata: dict[str, Any] = field(default_factory=dict)


class SearchAdapter(Protocol):
    def search(self, query: str, *, max_results: int) -> list[SearchResult]:
        """Return normalized search results for a research query."""


class SearchProviderUnavailable(RuntimeError):
    """Raised when a configured provider cannot be used."""
