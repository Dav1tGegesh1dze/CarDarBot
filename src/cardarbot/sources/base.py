from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from cardarbot.domain.enums import SourceStatusMode
from cardarbot.domain.search_profiles import SearchFilterConfig
from cardarbot.domain.vehicles import NormalizedListing


@dataclass
class SourceFetchResult:
    """Result returned by a listing data source."""

    source_name: str
    status_mode: SourceStatusMode
    listings: list[NormalizedListing] = field(default_factory=list)
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseListingSource(ABC):
    """Abstract base class for pluggable car listing sources."""

    source_name: str = "base"

    @abstractmethod
    async def fetch_listings(
        self,
        filters: SearchFilterConfig | None = None,
        max_pages: int = 1,
    ) -> SourceFetchResult:
        """Fetch and normalize listings matching the optional filter configuration."""
