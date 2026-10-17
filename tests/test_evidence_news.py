"""
Tests for NewsAPI mock and live providers.

The live (NewsAPIProvider) tests verify request construction, error handling,
and API response parsing WITHOUT making real HTTP calls (using httpx mock).
No real NEWS_API_KEY is required for the ordinary test suite.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.evidence.providers.news.mock_provider import MockNewsProvider
from src.evidence.providers.news.newsapi_provider import NewsAPIProvider
from src.evidence.schemas import EvidenceStatus, SourceMode


# ---------------------------------------------------------------------------
# Mock news provider tests
# ---------------------------------------------------------------------------

class TestMockNewsProvider:

    def setup_method(self):
        self.provider = MockNewsProvider()

    def test_known_entity_returns_match_found(self):
        r = self.provider.search("Synthetic Fraudster One")
        assert r.status == EvidenceStatus.MATCH_FOUND

    def test_known_entity_articles_not_empty(self):
        r = self.provider.search("Synthetic Fraudster One")
        assert len(r.data.articles) >= 1

    def test_article_has_required_fields(self):
        r = self.provider.search("Synthetic Fraudster One")
        article = r.data.articles[0]
        assert isinstance(article.title, str)
        assert isinstance(article.source, str)

    def test_unknown_entity_returns_no_articles(self):
        r = self.provider.search("Completely Unknown Entity XYZ123")
        assert r.status == EvidenceStatus.NO_ARTICLES

    def test_unknown_entity_empty_article_list(self):
        r = self.provider.search("Completely Unknown Entity XYZ123")
        assert r.data.articles == []

    def test_empty_results_are_not_marked_match_found(self):
        r = self.provider.search("Clean User (SYNTHETIC)")
        assert r.status == EvidenceStatus.NO_ARTICLES

    def test_source_mode_is_mock(self):
        r = self.provider.search("Synthetic Fraudster One")
        assert r.source_mode == SourceMode.MOCK

    def test_repeated_calls_are_deterministic(self):
        r1 = self.provider.search("Synthetic Fraudster One")
        r2 = self.provider.search("Synthetic Fraudster One")
        assert len(r1.data.articles) == len(r2.data.articles)
        for a1, a2 in zip(r1.data.articles, r2.data.articles):
            assert a1.title == a2.title
            assert a1.source == a2.source

    def test_no_articles_warning_present(self):
        r = self.provider.search("Clean User (SYNTHETIC)")
        warning_text = " ".join(r.warnings).lower()
        assert "no articles" in warning_text

    def test_interpretation_warning_present_in_data(self):
        r = self.provider.search("Synthetic Fraudster One")
        assert "does not prove" in r.data.interpretation_warning.lower() or \
               "no articles found" in r.data.interpretation_warning.lower()

    def test_max_articles_limit_respected(self):
        r = self.provider.search("Synthetic Fraudster One", max_articles=1)
        assert len(r.data.articles) <= 1


# ---------------------------------------------------------------------------
# Live (NewsAPIProvider) tests — no real HTTP calls
# ---------------------------------------------------------------------------

class TestNewsAPIProviderMissingKey:

    def test_missing_key_returns_auth_error(self):
        """If NEWS_API_KEY is not set, provider must return AUTH_ERROR immediately."""
        provider = NewsAPIProvider()
        with patch.dict("os.environ", {}, clear=True):
            # Ensure NEWS_API_KEY is absent
            import os
            os.environ.pop("NEWS_API_KEY", None)
            r = provider.search("test query")
        assert r.status == EvidenceStatus.AUTH_ERROR

    def test_missing_key_error_message_present(self):
        provider = NewsAPIProvider()
        with patch.dict("os.environ", {}, clear=True):
            import os
            os.environ.pop("NEWS_API_KEY", None)
            r = provider.search("test query")
        assert len(r.errors) > 0

    def test_missing_key_does_not_expose_key_value(self):
        """Error messages must not include any credential value."""
        provider = NewsAPIProvider()
        with patch.dict("os.environ", {}, clear=True):
            import os
            os.environ.pop("NEWS_API_KEY", None)
            r = provider.search("test query")
        # The key is absent so there is nothing to expose, but the error
        # message itself must not accidentally print any credential pattern.
        for err in r.errors:
            assert "gsk_" not in err      # Groq key pattern
            assert "d827ec" not in err    # Specific key prefix pattern


class TestNewsAPIProviderHTTPErrors:
    """Test live provider error handling via mocked httpx responses."""

    def _make_mock_response(self, status_code: int, body: dict | str | None = None):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        if isinstance(body, dict):
            mock_resp.json.return_value = body
        elif body is None:
            mock_resp.json.side_effect = Exception("not json")
        return mock_resp

    def test_401_returns_auth_error(self):
        provider = NewsAPIProvider()
        with patch.dict("os.environ", {"NEWS_API_KEY": "fake-key-for-test"}):
            with patch("src.evidence.providers.news.newsapi_provider.httpx.get") as mock_get:
                mock_get.return_value = self._make_mock_response(401)
                r = provider.search("test")
        assert r.status == EvidenceStatus.AUTH_ERROR

    def test_429_returns_auth_error(self):
        provider = NewsAPIProvider()
        with patch.dict("os.environ", {"NEWS_API_KEY": "fake-key-for-test"}):
            with patch("src.evidence.providers.news.newsapi_provider.httpx.get") as mock_get:
                mock_get.return_value = self._make_mock_response(429)
                r = provider.search("test")
        assert r.status == EvidenceStatus.AUTH_ERROR

    def test_500_returns_provider_error(self):
        provider = NewsAPIProvider()
        with patch.dict("os.environ", {"NEWS_API_KEY": "fake-key-for-test"}):
            with patch("src.evidence.providers.news.newsapi_provider.httpx.get") as mock_get:
                mock_get.return_value = self._make_mock_response(500)
                r = provider.search("test")
        assert r.status == EvidenceStatus.PROVIDER_ERROR

    def test_timeout_returns_provider_error(self):
        import httpx as _httpx
        provider = NewsAPIProvider()
        with patch.dict("os.environ", {"NEWS_API_KEY": "fake-key-for-test"}):
            with patch("src.evidence.providers.news.newsapi_provider.httpx.get") as mock_get:
                mock_get.side_effect = _httpx.TimeoutException("timed out")
                r = provider.search("test")
        assert r.status == EvidenceStatus.PROVIDER_ERROR

    def test_malformed_json_returns_provider_error(self):
        provider = NewsAPIProvider()
        with patch.dict("os.environ", {"NEWS_API_KEY": "fake-key-for-test"}):
            with patch("src.evidence.providers.news.newsapi_provider.httpx.get") as mock_get:
                mock_get.return_value = self._make_mock_response(200, None)
                r = provider.search("test")
        assert r.status == EvidenceStatus.PROVIDER_ERROR

    def test_newsapi_error_status_returns_provider_error(self):
        provider = NewsAPIProvider()
        error_body = {"status": "error", "code": "apiKeyInvalid", "message": "Your API key is invalid."}
        with patch.dict("os.environ", {"NEWS_API_KEY": "fake-key-for-test"}):
            with patch("src.evidence.providers.news.newsapi_provider.httpx.get") as mock_get:
                mock_get.return_value = self._make_mock_response(200, error_body)
                r = provider.search("test")
        assert r.status == EvidenceStatus.PROVIDER_ERROR

    def test_successful_response_with_articles_returns_match_found(self):
        provider = NewsAPIProvider()
        good_body = {
            "status": "ok",
            "totalResults": 1,
            "articles": [
                {
                    "title": "Test Article",
                    "source": {"name": "Test Source"},
                    "publishedAt": "2024-01-10T08:00:00Z",
                    "url": "https://example.com/article",
                    "description": "Test description.",
                }
            ],
        }
        with patch.dict("os.environ", {"NEWS_API_KEY": "fake-key-for-test"}):
            with patch("src.evidence.providers.news.newsapi_provider.httpx.get") as mock_get:
                mock_get.return_value = self._make_mock_response(200, good_body)
                r = provider.search("test entity")
        assert r.status == EvidenceStatus.MATCH_FOUND
        assert len(r.data.articles) == 1
        assert r.data.articles[0].title == "Test Article"

    def test_successful_response_no_articles_returns_no_articles(self):
        provider = NewsAPIProvider()
        empty_body = {"status": "ok", "totalResults": 0, "articles": []}
        with patch.dict("os.environ", {"NEWS_API_KEY": "fake-key-for-test"}):
            with patch("src.evidence.providers.news.newsapi_provider.httpx.get") as mock_get:
                mock_get.return_value = self._make_mock_response(200, empty_body)
                r = provider.search("obscure entity")
        assert r.status == EvidenceStatus.NO_ARTICLES
        assert r.data.articles == []

    def test_live_source_mode(self):
        provider = NewsAPIProvider()
        empty_body = {"status": "ok", "totalResults": 0, "articles": []}
        with patch.dict("os.environ", {"NEWS_API_KEY": "fake-key-for-test"}):
            with patch("src.evidence.providers.news.newsapi_provider.httpx.get") as mock_get:
                mock_get.return_value = self._make_mock_response(200, empty_body)
                r = provider.search("test")
        assert r.source_mode == SourceMode.LIVE

    def test_api_key_not_in_response_content(self):
        """API key must never appear in any response field."""
        fake_key = "fake-key-for-test-UNIQUE-VALUE"
        provider = NewsAPIProvider()
        empty_body = {"status": "ok", "totalResults": 0, "articles": []}
        with patch.dict("os.environ", {"NEWS_API_KEY": fake_key}):
            with patch("src.evidence.providers.news.newsapi_provider.httpx.get") as mock_get:
                mock_get.return_value = self._make_mock_response(200, empty_body)
                r = provider.search("test")
        response_json = r.model_dump_json()
        assert fake_key not in response_json

    def test_request_error_returns_provider_error(self):
        import httpx as _httpx
        provider = NewsAPIProvider()
        with patch.dict("os.environ", {"NEWS_API_KEY": "fake-key-for-test"}):
            with patch("src.evidence.providers.news.newsapi_provider.httpx.get") as mock_get:
                mock_get.side_effect = _httpx.RequestError("connection refused")
                r = provider.search("test")
        assert r.status == EvidenceStatus.PROVIDER_ERROR
