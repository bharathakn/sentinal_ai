"""
Sentinel AI — Phase 5: Evidence services FastAPI application.

This application exposes all seven evidence provider interfaces as REST
endpoints. It is a single modular application — not seven separate servers.

Endpoints
---------
GET  /health
GET  /evidence/banking/{account_id}
GET  /evidence/kyc/{account_id}
GET  /evidence/device/{account_id}/{device_id}
GET  /evidence/beneficiary/{account_id}
POST /evidence/sanctions/screen-subject
POST /evidence/sanctions/screen-account
GET  /evidence/geolocation/{account_id}
POST /evidence/news/search

All responses are JSON-serializable Pydantic models.
OpenAPI docs: GET /docs
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from .config import get_news_provider_mode, NewsProviderMode
from .providers import (
    check_device,
    check_geolocation,
    get_account_history,
    get_beneficiary,
    get_kyc_data,
    screen_account,
    screen_subject,
    MockNewsProvider,
    NewsAPIProvider,
)
from .schemas import (
    CoreBankingResponse,
    DeviceRegistryResponse,
    BeneficiaryResponse,
    GeolocationResponse,
    KYCResponse,
    NewsResponse,
    SanctionsResponse,
)

app = FastAPI(
    title="Sentinel AI — Mock Evidence Services",
    description=(
        "Phase 5 mock evidence infrastructure for Sentinel AI. "
        "Six of seven sources are synthetic mocks. "
        "NewsAPI may use a live external provider when configured."
    ),
    version="0.5.0",
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
def health() -> dict:
    """Lightweight health check endpoint."""
    return {"status": "ok", "service": "sentinel-ai-evidence", "phase": "5"}


# ---------------------------------------------------------------------------
# Core Banking
# ---------------------------------------------------------------------------

@app.get(
    "/evidence/banking/{account_id}",
    response_model=CoreBankingResponse,
    tags=["Core Banking"],
    summary="Retrieve synthetic transaction history for an account.",
)
def get_banking(account_id: str) -> CoreBankingResponse:
    """Return mock core banking transaction history and statistics.

    - **account_id**: Known fixture accounts: ACC001, ACC002, ACC003, ACC004.
    - Unknown accounts return status NOT_FOUND.
    """
    return get_account_history(account_id)


# ---------------------------------------------------------------------------
# KYC
# ---------------------------------------------------------------------------

@app.get(
    "/evidence/kyc/{account_id}",
    response_model=KYCResponse,
    tags=["KYC"],
    summary="Retrieve synthetic KYC customer profile.",
)
def get_kyc(account_id: str) -> KYCResponse:
    """Return mock KYC profile for the account.

    - **account_id**: Known fixture accounts: ACC001, ACC002, ACC003, ACC004.
    """
    return get_kyc_data(account_id)


# ---------------------------------------------------------------------------
# Device Registry
# ---------------------------------------------------------------------------

@app.get(
    "/evidence/device/{account_id}/{device_id}",
    response_model=DeviceRegistryResponse,
    tags=["Device Registry"],
    summary="Check device registration status for an account.",
)
def get_device(account_id: str, device_id: str) -> DeviceRegistryResponse:
    """Return mock device registration data.

    - **account_id**: Known fixture accounts: ACC001–ACC004.
    - **device_id**: Known fixture devices: DEV001 (registered), DEV002 (new), DEV003 (shared).
    """
    return check_device(account_id, device_id)


# ---------------------------------------------------------------------------
# Beneficiary
# ---------------------------------------------------------------------------

@app.get(
    "/evidence/beneficiary/{account_id}",
    response_model=BeneficiaryResponse,
    tags=["Beneficiary"],
    summary="Retrieve synthetic beneficiary account profile.",
)
def get_beneficiary_endpoint(account_id: str) -> BeneficiaryResponse:
    """Return mock beneficiary profile.

    - **account_id**: Known fixture accounts: ACC001–ACC004.
    """
    return get_beneficiary(account_id)


# ---------------------------------------------------------------------------
# Sanctions
# ---------------------------------------------------------------------------

class SanctionsSubjectRequest(BaseModel):
    subject_query: str


class SanctionsAccountRequest(BaseModel):
    account_id: str


@app.post(
    "/evidence/sanctions/screen-subject",
    response_model=SanctionsResponse,
    tags=["Sanctions"],
    summary="Screen a subject name against the mock watchlist.",
)
def screen_subject_endpoint(request: SanctionsSubjectRequest) -> SanctionsResponse:
    """Screen a subject name against the synthetic mock watchlist.

    - Use 'SANC001' or 'Synthetic Fraudster One' for a match result.
    - All other queries return no-match.
    - **No real sanctions database is consulted.**
    """
    return screen_subject(request.subject_query)


@app.post(
    "/evidence/sanctions/screen-account",
    response_model=SanctionsResponse,
    tags=["Sanctions"],
    summary="Screen an account ID against the mock watchlist.",
)
def screen_account_endpoint(request: SanctionsAccountRequest) -> SanctionsResponse:
    """Screen an account by its ID using the synthetic mock watchlist mapping.

    - ACC004 maps to the synthetic flagged subject (MATCH_FOUND).
    - ACC001, ACC002, ACC003 map to no-match subjects.
    """
    return screen_account(request.account_id)


# ---------------------------------------------------------------------------
# Geolocation
# ---------------------------------------------------------------------------

@app.get(
    "/evidence/geolocation/{account_id}",
    response_model=GeolocationResponse,
    tags=["Geolocation"],
    summary="Compare transaction location with registered account location.",
)
def get_geolocation(
    account_id: str,
    lat: Optional[float] = Query(default=None, description="Transaction latitude"),
    lon: Optional[float] = Query(default=None, description="Transaction longitude"),
    city: Optional[str] = Query(default=None, description="Transaction city"),
    country: Optional[str] = Query(default=None, description="Transaction country"),
) -> GeolocationResponse:
    """Return mock geolocation analysis.

    Computes Haversine distance between transaction and registered locations.
    Flags as anomalous when distance >= 500 km.
    Missing coordinates return is_anomalous=None (not False).
    """
    return check_geolocation(
        account_id=account_id,
        transaction_latitude=lat,
        transaction_longitude=lon,
        transaction_city=city,
        transaction_country=country,
    )


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------

class NewsSearchRequest(BaseModel):
    query: str
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    max_articles: int = 10


def _get_news_provider():
    """Select news provider based on configuration. Explicit — never silent fallback."""
    mode = get_news_provider_mode()
    if mode == NewsProviderMode.LIVE:
        return NewsAPIProvider()
    return MockNewsProvider()


@app.post(
    "/evidence/news/search",
    response_model=NewsResponse,
    tags=["News"],
    summary="Search news for an entity using the configured news provider.",
)
def search_news(request: NewsSearchRequest) -> NewsResponse:
    """Search for news articles.

    Provider is selected by SENTINEL_NEWS_PROVIDER env var:
    - 'mock' (default): deterministic mock fixture, no external calls.
    - 'live': real NewsAPI call, requires NEWS_API_KEY env var.

    No articles found does NOT mean no adverse news exists.
    """
    provider = _get_news_provider()
    return provider.search(
        query=request.query,
        from_date=request.from_date,
        to_date=request.to_date,
        max_articles=request.max_articles,
    )
