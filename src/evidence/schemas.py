"""
Sentinel AI — Phase 5: Shared evidence response schema.

All seven evidence providers return responses conforming to models defined
here. This ensures Agent 2 can consume any provider result through a single
predictable contract.

Design rules
------------
* `source_mode` = "MOCK" for synthetic providers; "LIVE" for real APIs.
* `status` values are distinct and must not be conflated:
    - FOUND            : Evidence retrieved and entity recognised.
    - NOT_FOUND        : Provider responded but entity not in records.
    - NO_MATCH         : Screening returned no match (sanctions / news).
    - MATCH_FOUND      : Screening returned a match (sanctions / news).
    - VALIDATION_ERROR : Bad request / invalid input.
    - PROVIDER_ERROR   : Provider failure or timeout.
    - AUTH_ERROR       : API authentication or rate-limit error.
    - NO_ARTICLES      : News search returned zero articles (distinct from error).
* `None` is used for genuinely absent values; empty list [] is used for
  absent lists. Neither is substituted for a genuine missing-data case.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class EvidenceStatus(str, Enum):
    """Outcome status of an evidence retrieval request."""

    FOUND = "FOUND"
    """Provider responded; entity recognised; evidence data is present."""

    NOT_FOUND = "NOT_FOUND"
    """Provider responded; entity not in records (unknown account/device/etc)."""

    NO_MATCH = "NO_MATCH"
    """Screening / search returned no match (sanctions, news). Not the same as NOT_FOUND."""

    MATCH_FOUND = "MATCH_FOUND"
    """Screening / search returned at least one match."""

    NO_ARTICLES = "NO_ARTICLES"
    """News search completed; zero articles returned. Not proof of no adverse news."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    """Request contained invalid fields or missing required identifiers."""

    PROVIDER_ERROR = "PROVIDER_ERROR"
    """Provider unavailable, timed out, or returned a malformed response."""

    AUTH_ERROR = "AUTH_ERROR"
    """API authentication failure or rate-limit exceeded."""


class SourceMode(str, Enum):
    """Distinguishes mock synthetic evidence from live external evidence."""

    MOCK = "MOCK"
    """Result produced by a deterministic synthetic mock provider."""

    LIVE = "LIVE"
    """Result produced by a real external API call."""


# ---------------------------------------------------------------------------
# Base response model
# ---------------------------------------------------------------------------


class EvidenceResponse(BaseModel):
    """Base response envelope for all seven evidence providers.

    All provider responses extend this model with `data` and any
    provider-specific fields.
    """

    model_config = ConfigDict(frozen=True)

    source: str = Field(description="Provider name (e.g. 'MOCK_CORE_BANKING').")
    source_mode: SourceMode = Field(description="MOCK or LIVE.")
    status: EvidenceStatus = Field(description="Outcome status of the request.")
    requested_entity_id: Optional[str] = Field(
        default=None,
        description="Primary entity identifier from the request.",
    )
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this response was produced.",
    )
    request_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this evidence request.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings (e.g. partial data, incomplete match).",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Error messages when status is PROVIDER_ERROR or AUTH_ERROR.",
    )


# ---------------------------------------------------------------------------
# Transaction history sub-models
# ---------------------------------------------------------------------------


class TransactionRecord(BaseModel):
    """A single transaction record in core banking history."""

    model_config = ConfigDict(frozen=True)

    tx_id: str
    counterparty_id: str
    amount_inr: float
    direction: str   # "DEBIT" or "CREDIT"
    channel: str
    timestamp: datetime
    description: str


class AccountStats(BaseModel):
    """Pre-computed statistics for a core banking account."""

    model_config = ConfigDict(frozen=True)

    num_transactions_30d: int
    avg_debit_amount_inr: float
    max_debit_30d_inr: float
    known_beneficiaries: list[str]
    tx_frequency_per_week: float
    computation_note: str


class CoreBankingData(BaseModel):
    """Data payload for core banking evidence responses."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    account_type: Optional[str] = None
    bank_name: Optional[str] = None
    transaction_history: list[TransactionRecord] = Field(default_factory=list)
    stats: Optional[AccountStats] = None
    synthetic_notice: Optional[str] = None


class CoreBankingResponse(EvidenceResponse):
    """Evidence response from the core banking provider."""

    data: Optional[CoreBankingData] = Field(
        default=None,
        description="Account and transaction data. None when status != FOUND.",
    )


# ---------------------------------------------------------------------------
# KYC sub-models
# ---------------------------------------------------------------------------


class KYCData(BaseModel):
    """Data payload for KYC evidence responses."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    kyc_status: str
    pep: Optional[bool] = None
    account_type: Optional[str] = None
    account_opening_date: Optional[datetime] = None
    occupation: Optional[str] = None
    income_band: Optional[str] = None
    registered_city: Optional[str] = None
    registered_state: Optional[str] = None
    registered_country: Optional[str] = None
    synthetic_notice: Optional[str] = None


class KYCResponse(EvidenceResponse):
    """Evidence response from the KYC provider."""

    data: Optional[KYCData] = Field(default=None)


# ---------------------------------------------------------------------------
# Device registry sub-models
# ---------------------------------------------------------------------------


class DeviceRegistryData(BaseModel):
    """Data payload for device registry evidence responses."""

    model_config = ConfigDict(frozen=True)

    device_id: str
    account_id: str
    registration_status: str
    device_type: Optional[str] = None
    device_info: Optional[str] = None
    device_fingerprint: Optional[str] = None
    associated_accounts: list[str] = Field(default_factory=list)
    first_seen: Optional[datetime] = None
    num_associated_accounts: int = 0
    is_registered_to_account: bool = False
    synthetic_notice: Optional[str] = None


class DeviceRegistryResponse(EvidenceResponse):
    """Evidence response from the device registry provider."""

    data: Optional[DeviceRegistryData] = Field(default=None)


# ---------------------------------------------------------------------------
# Beneficiary sub-models
# ---------------------------------------------------------------------------


class BeneficiaryData(BaseModel):
    """Data payload for beneficiary evidence responses."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    customer_name: Optional[str] = None
    account_opening_date: Optional[datetime] = None
    account_age_days: Optional[int] = None
    kyc_status: Optional[str] = None
    bank_name: Optional[str] = None
    known_transaction_count: int = 0
    previous_fraud_flag: bool = False
    linked_accounts: list[str] = Field(default_factory=list)
    synthetic_notice: Optional[str] = None


class BeneficiaryResponse(EvidenceResponse):
    """Evidence response from the beneficiary provider."""

    data: Optional[BeneficiaryData] = Field(default=None)


# ---------------------------------------------------------------------------
# Sanctions sub-models
# ---------------------------------------------------------------------------


class SanctionsData(BaseModel):
    """Data payload for sanctions screening responses."""

    model_config = ConfigDict(frozen=True)

    subject_query: str
    matched: bool
    list_name: Optional[str] = None
    match_detail: Optional[str] = None
    match_confidence: Optional[str] = None
    matching_method: Optional[str] = None
    list_date: Optional[datetime] = None
    screening_disclaimer: str = (
        "MOCK RESULT — No real sanctions database was consulted. "
        "This is a synthetic prototype result for testing only."
    )
    synthetic_notice: Optional[str] = None


class SanctionsResponse(EvidenceResponse):
    """Evidence response from the sanctions screening provider."""

    data: Optional[SanctionsData] = Field(default=None)


# ---------------------------------------------------------------------------
# Geolocation sub-models
# ---------------------------------------------------------------------------


class GeolocationData(BaseModel):
    """Data payload for geolocation evidence responses."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    transaction_city: Optional[str] = None
    transaction_country: Optional[str] = None
    transaction_latitude: Optional[float] = None
    transaction_longitude: Optional[float] = None
    registered_city: Optional[str] = None
    registered_country: Optional[str] = None
    registered_latitude: Optional[float] = None
    registered_longitude: Optional[float] = None
    distance_km: Optional[float] = None
    is_anomalous: Optional[bool] = None
    anomaly_reason: Optional[str] = None
    location_data_available: bool = True
    synthetic_notice: Optional[str] = None


class GeolocationResponse(EvidenceResponse):
    """Evidence response from the geolocation provider."""

    data: Optional[GeolocationData] = Field(default=None)


# ---------------------------------------------------------------------------
# News sub-models
# ---------------------------------------------------------------------------


class NewsArticle(BaseModel):
    """A single news article result."""

    model_config = ConfigDict(frozen=True)

    title: str
    source: str
    published_at: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    synthetic_notice: Optional[str] = None


class NewsData(BaseModel):
    """Data payload for news search responses."""

    model_config = ConfigDict(frozen=True)

    query: str
    articles: list[NewsArticle] = Field(default_factory=list)
    total_results: int = 0
    provider_name: str
    interpretation_warning: str = (
        "No articles found does not prove no adverse information exists. "
        "Articles mentioning similarly named entities are preserved for review "
        "and must not be treated as confirmed matches without further verification."
    )


class NewsResponse(EvidenceResponse):
    """Evidence response from the news search provider."""

    data: Optional[NewsData] = Field(default=None)
