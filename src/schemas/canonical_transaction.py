"""
Sentinel AI — Canonical Transaction Schema

This module defines the canonical internal transaction representation used
across all Sentinel AI agents. Every raw dataset (IEEE-CIS, PaySim, India
Synthetic) is normalized into this schema before entering the agent pipeline.

Design principles:
  - Agents work with CanonicalTransaction, never with raw dataset columns.
  - All optional fields are explicitly Optional to handle dataset gaps.
  - Source provenance is always preserved (source_dataset, raw_record_id).
  - Pydantic v2 validators enforce business rules at ingestion time.
  - Currency is stored as an ISO-4217 string; amounts are always Decimal.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class TransactionChannel(str, Enum):
    """Payment channel through which the transaction was initiated."""

    UPI = "UPI"            # India Unified Payments Interface
    NEFT = "NEFT"          # India National Electronic Funds Transfer
    RTGS = "RTGS"          # India Real Time Gross Settlement
    IMPS = "IMPS"          # India Immediate Payment Service
    CARD = "CARD"          # Card-present / card-not-present
    WIRE = "WIRE"          # International/domestic wire transfer
    ACH = "ACH"            # Automated Clearing House (US)
    MOBILE = "MOBILE"      # Generic mobile-banking initiated
    ONLINE = "ONLINE"      # Internet banking / e-commerce
    CASH = "CASH"          # Cash deposit / withdrawal
    PAYMENT = "PAYMENT"    # Generic merchant payment (PaySim type)
    TRANSFER = "TRANSFER"  # Generic account-to-account transfer
    CASH_OUT = "CASH_OUT"  # Cash-out (PaySim type)
    CASH_IN = "CASH_IN"    # Cash-in (PaySim type)
    DEBIT = "DEBIT"        # Debit (PaySim type)
    UNKNOWN = "UNKNOWN"    # Channel could not be determined


class TransactionStatus(str, Enum):
    """Outcome / settlement status of the transaction."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING = "PENDING"
    REVERSED = "REVERSED"
    UNKNOWN = "UNKNOWN"


class DataSource(str, Enum):
    """Originating dataset / system that produced this record."""

    IEEE_CIS = "IEEE_CIS"
    PAYSIM = "PAYSIM"
    INDIA_SYNTHETIC = "INDIA_SYNTHETIC"
    LIVE_BANKING = "LIVE_BANKING"      # Future production source
    MOCK_BANKING = "MOCK_BANKING"      # Prototype mock banking API
    UPLOADED_DATASET = "UPLOADED_DATASET"  # Analyst-uploaded file (India column layout); origin unverified
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class GeoLocation(BaseModel):
    """Geographic coordinates and human-readable location metadata."""

    model_config = ConfigDict(frozen=True)

    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    zip_code: Optional[str] = None

    @field_validator("latitude")
    @classmethod
    def latitude_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (-90.0 <= v <= 90.0):
            raise ValueError(f"latitude must be in [-90, 90], got {v}")
        return v

    @field_validator("longitude")
    @classmethod
    def longitude_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (-180.0 <= v <= 180.0):
            raise ValueError(f"longitude must be in [-180, 180], got {v}")
        return v


class DeviceInfo(BaseModel):
    """Device and session metadata at the time of the transaction."""

    model_config = ConfigDict(frozen=True)

    device_id: Optional[str] = None
    device_type: Optional[str] = None   # e.g. "mobile", "desktop"
    device_info: Optional[str] = None   # raw device-info string (IEEE-CIS)
    ip_address: Optional[str] = None
    is_new_device: Optional[bool] = None


class AccountInfo(BaseModel):
    """Normalised account-level information for a transaction party."""

    model_config = ConfigDict(frozen=True)

    account_id: Optional[str] = None
    customer_id: Optional[str] = None
    vpa: Optional[str] = None             # UPI Virtual Payment Address
    ifsc_code: Optional[str] = None       # Indian bank branch code
    email_domain: Optional[str] = None    # e-mail domain (IEEE-CIS)
    balance_before: Optional[Decimal] = None
    balance_after: Optional[Decimal] = None
    account_name: Optional[str] = None    # PaySim nameOrig / nameDest


class TransactionMetadata(BaseModel):
    """
    Dataset-specific supplementary features that do not fit the canonical
    core but must be preserved for downstream ML agents.

    Stored as a typed bag-of-words dict so adapters can pass through any
    extra columns without losing information.
    """

    model_config = ConfigDict(frozen=True)

    # ML / risk features
    anomaly_score: Optional[float] = None
    amount_ratio_vs_30d_avg: Optional[float] = None
    tx_frequency_24h: Optional[int] = None
    time_since_last_tx_sec: Optional[int] = None
    distance_from_home_km: Optional[float] = None
    is_new_beneficiary: Optional[bool] = None
    time_since_beneficiary_added_min: Optional[int] = None

    # IEEE-CIS specific
    product_code: Optional[str] = None
    card_type: Optional[str] = None      # e.g. "credit", "debit"
    card_network: Optional[str] = None   # e.g. "visa", "mastercard"

    # PaySim specific
    paysim_step: Optional[int] = None    # simulation time-step (hour)
    is_flagged_fraud: Optional[bool] = None

    # India Synthetic specific
    scenario_id: Optional[str] = None
    risk_label: Optional[str] = None
    alert_id: Optional[str] = None
    transaction_type: Optional[str] = None  # e.g. "P2P", "C2B"

    # Carry-all for any extra adapter-specific fields
    extra: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Canonical Transaction
# ---------------------------------------------------------------------------


class CanonicalTransaction(BaseModel):
    """
    Sentinel AI Canonical Transaction Representation.

    This is the single, unified internal schema for all financial transactions
    across the system. Every dataset adapter must produce a valid instance of
    this model. Every Sentinel AI agent must consume this model as its primary
    transaction input.

    Provenance fields (source_dataset, raw_record_id) are mandatory so that
    every canonical record can be traced back to its origin.
    """

    model_config = ConfigDict(frozen=True, use_enum_values=True)

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    canonical_id: UUID = Field(
        default_factory=uuid4,
        description="Stable internal UUID assigned at canonicalization time.",
    )
    raw_record_id: str = Field(
        description="Primary identifier from the originating dataset (e.g. TransactionID).",
    )
    source_dataset: DataSource = Field(
        description="Originating dataset that produced this record.",
    )

    # ------------------------------------------------------------------
    # Core transaction fields
    # ------------------------------------------------------------------
    amount: Decimal = Field(
        description="Transaction amount in the stated currency.",
        ge=Decimal("0"),
    )
    currency: str = Field(
        default="USD",
        description="ISO-4217 currency code.",
        min_length=3,
        max_length=3,
    )
    timestamp: Optional[datetime] = Field(
        default=None,
        description="Transaction initiation timestamp (UTC or offset-aware).",
    )
    channel: TransactionChannel = Field(
        default=TransactionChannel.UNKNOWN,
        description="Payment channel used for the transaction.",
    )
    status: TransactionStatus = Field(
        default=TransactionStatus.UNKNOWN,
        description="Settlement / outcome status.",
    )

    # ------------------------------------------------------------------
    # Parties
    # ------------------------------------------------------------------
    sender: AccountInfo = Field(
        default_factory=AccountInfo,
        description="Originating account (sender / payor).",
    )
    receiver: AccountInfo = Field(
        default_factory=AccountInfo,
        description="Destination account (receiver / payee / beneficiary).",
    )

    # ------------------------------------------------------------------
    # Device & Location
    # ------------------------------------------------------------------
    device: DeviceInfo = Field(
        default_factory=DeviceInfo,
        description="Device and session metadata.",
    )
    location: GeoLocation = Field(
        default_factory=GeoLocation,
        description="Geographic location metadata.",
    )

    # ------------------------------------------------------------------
    # Ground-truth labels (present in labelled datasets, absent in live)
    # ------------------------------------------------------------------
    is_fraud: Optional[bool] = Field(
        default=None,
        description="Ground-truth fraud label (only available in labelled datasets).",
    )

    # ------------------------------------------------------------------
    # Additional metadata
    # ------------------------------------------------------------------
    metadata: TransactionMetadata = Field(
        default_factory=TransactionMetadata,
        description="Dataset-specific supplementary features.",
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, v: str) -> str:
        return v.upper()

    @field_validator("amount", mode="before")
    @classmethod
    def amount_to_decimal(cls, v: Any) -> Decimal:
        try:
            return Decimal(str(v))
        except Exception as exc:
            raise ValueError(f"amount must be numeric, got {v!r}") from exc

    @model_validator(mode="after")
    def amount_positive(self) -> "CanonicalTransaction":
        if self.amount < Decimal("0"):
            raise ValueError(f"amount must be >= 0, got {self.amount}")
        return self

    @model_validator(mode="after")
    def raw_record_id_not_empty(self) -> "CanonicalTransaction":
        if not self.raw_record_id or not self.raw_record_id.strip():
            raise ValueError("raw_record_id must not be empty")
        return self
