"""Sentinel AI — Deterministic mock news provider.

Returns synthetic article data from fixture_data.py.
Makes NO external HTTP calls. Safe for all automated tests.
"""

from __future__ import annotations

from typing import Optional

from ...fixture_data import get_news_articles, SYNTHETIC_DATA_NOTICE
from ...schemas import (
    EvidenceStatus,
    NewsArticle,
    NewsData,
    NewsResponse,
    SourceMode,
)
from .base import BaseNewsProvider

_SOURCE = "MOCK_NEWS_PROVIDER"


class MockNewsProvider(BaseNewsProvider):
    """Deterministic mock news provider.

    Returns fixture articles from fixture_data.py. Identical queries
    always produce identical results (no randomness, no external calls).
    """

    def search(
        self,
        query: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        max_articles: int = 10,
    ) -> NewsResponse:
        """Return synthetic article data for the query.

        Empty results mean the mock fixture has no articles for this query.
        Empty results do NOT prove no adverse news exists in reality.
        """
        raw_articles = get_news_articles(query)[:max_articles]

        articles = [
            NewsArticle(
                title=a["title"],
                source=a["source"],
                published_at=a.get("published_at"),
                url=a.get("url"),
                description=a.get("description"),
                synthetic_notice=a.get("synthetic_notice", SYNTHETIC_DATA_NOTICE),
            )
            for a in raw_articles
        ]

        status = EvidenceStatus.MATCH_FOUND if articles else EvidenceStatus.NO_ARTICLES

        data = NewsData(
            query=query,
            articles=articles,
            total_results=len(articles),
            provider_name=_SOURCE,
        )

        warnings = []
        if status == EvidenceStatus.NO_ARTICLES:
            warnings.append(
                "No articles found for this query in the mock news fixture. "
                "This does not prove no adverse news exists."
            )

        return NewsResponse(
            source=_SOURCE,
            source_mode=SourceMode.MOCK,
            status=status,
            requested_entity_id=query,
            data=data,
            warnings=warnings,
        )
