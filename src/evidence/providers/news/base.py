"""Sentinel AI — Abstract news provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ...schemas import NewsResponse


class BaseNewsProvider(ABC):
    """Abstract base for all news provider implementations.

    Subclasses must implement `search()`. The caller selects the implementation
    at construction time. Mock and live implementations must not be silently
    substituted for each other.
    """

    @abstractmethod
    def search(
        self,
        query: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        max_articles: int = 10,
    ) -> NewsResponse:
        """Search for news articles matching the query.

        Parameters
        ----------
        query        : Search query (entity name, topic, etc.).
        from_date    : ISO date string 'YYYY-MM-DD' for earliest results (optional).
        to_date      : ISO date string 'YYYY-MM-DD' for latest results (optional).
        max_articles : Maximum articles to return.

        Returns
        -------
        NewsResponse with status MATCH_FOUND, NO_ARTICLES, PROVIDER_ERROR, or AUTH_ERROR.
        """
