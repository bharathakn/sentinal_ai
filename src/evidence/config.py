"""
Sentinel AI — Phase 5: Evidence service configuration.

Reads environment variables. Never logs or prints credential values.
NEWS_API_KEY is the only external credential in Phase 5.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Optional


class NewsProviderMode(str, Enum):
    """Selects which news provider implementation is used."""

    MOCK = "mock"
    """Deterministic synthetic mock — no external calls."""

    LIVE = "live"
    """Real NewsAPI HTTP calls — requires NEWS_API_KEY."""


def get_news_api_key() -> Optional[str]:
    """Return the NewsAPI key from the environment, or None if not set.

    Never call this in a log statement. Never include the return value in
    error messages or API responses.
    """
    return os.environ.get("NEWS_API_KEY") or None


def get_news_provider_mode() -> NewsProviderMode:
    """Return the configured news provider mode.

    Reads SENTINEL_NEWS_PROVIDER env var. Defaults to 'mock'.
    Set to 'live' only when NEWS_API_KEY is also set.
    """
    raw = os.environ.get("SENTINEL_NEWS_PROVIDER", "mock").lower().strip()
    if raw == "live":
        return NewsProviderMode.LIVE
    return NewsProviderMode.MOCK


NEWSAPI_BASE_URL = "https://newsapi.org/v2"
NEWSAPI_EVERYTHING_ENDPOINT = f"{NEWSAPI_BASE_URL}/everything"
NEWSAPI_DEFAULT_TIMEOUT_SEC = 10
NEWSAPI_MAX_ARTICLES = 10
