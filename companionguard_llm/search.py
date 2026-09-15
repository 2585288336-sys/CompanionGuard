from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    source_type: str = "public_web"


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, *, domains: list[str] | None = None, limit: int = 5) -> list[SearchResult]: ...


class SearchNotConfigured(RuntimeError):
    pass


class DisabledSearchProvider:
    """Explicit extension point for Layer 3 retrieval.

    v0.7 intentionally does not ship an autonomous web agent. A future search
    adapter can implement SearchProvider and feed official-source candidates to
    the existing Evidence Assistant + human review pipeline.
    """

    name = "disabled"

    def search(self, query: str, *, domains: list[str] | None = None, limit: int = 5) -> list[SearchResult]:
        raise SearchNotConfigured(
            "No external Search Provider is configured. Use manual official sources in the MVP, "
            "or add a provider adapter later without changing Layer 3 audit logic."
        )
