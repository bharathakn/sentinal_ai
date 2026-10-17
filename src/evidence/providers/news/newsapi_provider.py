"""
Sentinel AI — Real NewsAPI provider.

Makes HTTP calls to NewsAPI (https://newsapi.org). Requires NEWS_API_KEY
environment variable.

IMPORTANT:
- Never called in ordinary automated tests (use MockNewsProvider instead).
- The API key is never logged, never included in responses.
- Results are clearly labelled source_mode=LIVE.
- A missing API key returns AUTH_ERROR immediately without any HTTP call.
- Timeouts, HTTP errors, rate limits, and malformed responses are handled
  explicitly and returned as PROVIDER_ERROR or AUTH_ERROR.
- Empty results are returned as NO_ARTICLES — not as an error.
- Caller must not interpret NO_ARTICLES as proof of no adverse information.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from ...config import (
    NEWSAPI_DEFAULT_TIMEOUT_SEC,
    NEWSAPI_EVERYTHING_ENDPOINT,
    NEWSAPI_MAX_ARTICLES,
    get_news_api_key,
)
from ...schemas import (
    EvidenceStatus,
    NewsArticle,
    NewsData,
    NewsResponse,
    SourceMode,
)
from .base import BaseNewsProvider

logger = logging.getLogger(__name__)

_SOURCE = "NEWSAPI_LIVE"


class NewsAPIProvider(BaseNewsProvider):
    """Real NewsAPI provider.

    Requires NEWS_API_KEY environment variable. Never call this in
    automated tests without explicit integration-test marking.
    """

    def search(
        self,
        query: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        max_articles: int = NEWSAPI_MAX_ARTICLES,
    ) -> NewsResponse:
        """Search NewsAPI /v2/everything for articles matching query.

        Parameters
        ----------
        query        : Search query string.
        from_date    : ISO date 'YYYY-MM-DD' for earliest article date.
        to_date      : ISO date 'YYYY-MM-DD' for latest article date.
        max_articles : Maximum results to request (capped at 100 by NewsAPI).

        Returns
        -------
        NewsResponse — source_mode=LIVE, status reflects actual API outcome.
        """
        api_key = get_news_api_key()
        if not api_key:
            return NewsResponse(
                source=_SOURCE,
                source_mode=SourceMode.LIVE,
                status=EvidenceStatus.AUTH_ERROR,
                requested_entity_id=query,
                errors=[
                    "NEWS_API_KEY environment variable is not set. "
                    "Set it to a valid NewsAPI key to use the live provider."
                ],
            )

        params: dict[str, str | int] = {
            "q": query,
            "pageSize": min(max_articles, 100),
            "language": "en",
            "sortBy": "publishedAt",
        }
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        # Headers — key is in the header, never in a log message
        headers = {"X-Api-Key": api_key}

        try:
            response = httpx.get(
                NEWSAPI_EVERYTHING_ENDPOINT,
                params=params,
                headers=headers,
                timeout=NEWSAPI_DEFAULT_TIMEOUT_SEC,
            )
        except httpx.TimeoutException:
            logger.warning("NewsAPI request timed out for query '%s'.", query)
            return NewsResponse(
                source=_SOURCE,
                source_mode=SourceMode.LIVE,
                status=EvidenceStatus.PROVIDER_ERROR,
                requested_entity_id=query,
                errors=["NewsAPI request timed out."],
            )
        except httpx.RequestError as exc:
            logger.warning("NewsAPI HTTP request error for query '%s': %s", query, exc)
            return NewsResponse(
                source=_SOURCE,
                source_mode=SourceMode.LIVE,
                status=EvidenceStatus.PROVIDER_ERROR,
                requested_entity_id=query,
                errors=[f"NewsAPI HTTP request error: {type(exc).__name__}"],
            )

        # Handle auth and rate limit
        if response.status_code == 401:
            return NewsResponse(
                source=_SOURCE,
                source_mode=SourceMode.LIVE,
                status=EvidenceStatus.AUTH_ERROR,
                requested_entity_id=query,
                errors=["NewsAPI returned 401 Unauthorized. Check NEWS_API_KEY validity."],
            )
        if response.status_code == 429:
            return NewsResponse(
                source=_SOURCE,
                source_mode=SourceMode.LIVE,
                status=EvidenceStatus.AUTH_ERROR,
                requested_entity_id=query,
                errors=["NewsAPI returned 429 Too Many Requests (rate limit exceeded)."],
            )
        if response.status_code != 200:
            logger.warning(
                "NewsAPI returned HTTP %d for query '%s'.",
                response.status_code, query,
            )
            return NewsResponse(
                source=_SOURCE,
                source_mode=SourceMode.LIVE,
                status=EvidenceStatus.PROVIDER_ERROR,
                requested_entity_id=query,
                errors=[f"NewsAPI returned HTTP {response.status_code}."],
            )

        # Parse response
        try:
            payload = response.json()
        except Exception:
            logger.warning("NewsAPI returned non-JSON body for query '%s'.", query)
            return NewsResponse(
                source=_SOURCE,
                source_mode=SourceMode.LIVE,
                status=EvidenceStatus.PROVIDER_ERROR,
                requested_entity_id=query,
                errors=["NewsAPI returned a malformed (non-JSON) response."],
            )

        if payload.get("status") != "ok":
            code = payload.get("code", "unknown")
            message = payload.get("message", "Unknown error from NewsAPI.")
            logger.warning(
                "NewsAPI error status for query '%s': code=%s message=%s",
                query, code, message,
            )
            return NewsResponse(
                source=_SOURCE,
                source_mode=SourceMode.LIVE,
                status=EvidenceStatus.PROVIDER_ERROR,
                requested_entity_id=query,
                errors=[f"NewsAPI error: {message} (code: {code})"],
            )

        raw_articles = payload.get("articles") or []
        articles = []
        for raw in raw_articles:
            source_name = raw.get("source", {}).get("name") or "Unknown"
            articles.append(
                NewsArticle(
                    title=raw.get("title") or "(no title)",
                    source=source_name,
                    published_at=raw.get("publishedAt"),
                    url=raw.get("url"),
                    description=raw.get("description"),
                )
            )

        status = EvidenceStatus.MATCH_FOUND if articles else EvidenceStatus.NO_ARTICLES

        data = NewsData(
            query=query,
            articles=articles,
            total_results=payload.get("totalResults", len(articles)),
            provider_name=_SOURCE,
        )

        warnings = []
        if status == EvidenceStatus.NO_ARTICLES:
            warnings.append(
                "No articles found. This does not prove no adverse news exists."
            )
        if len(articles) > 0:
            warnings.append(
                "Articles mentioning similarly named entities are preserved for review. "
                "Do not treat article results as confirmed identity matches without verification."
            )

        return NewsResponse(
            source=_SOURCE,
            source_mode=SourceMode.LIVE,
            status=status,
            requested_entity_id=query,
            data=data,
            warnings=warnings,
        )
