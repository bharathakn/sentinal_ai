"""
Sentinel AI — Agent 2: Evidence Gatherer output schema.

Design rules
------------
* Every evidence result carries source, retrieved_at, status, and data.
* None is used for genuinely absent data — never 0 or empty-string sentinel.
* Failed provider results are preserved in the output; they are NOT silently
  dropped or converted into clean/negative findings.
* A provider failure (PROVIDER_ERROR / AUTH_ERROR) is distinct from a
  no-match result (NO_MATCH / NO_ARTICLES / NOT_FOUND).
* Missing evidence must never be interpreted as safe evidence.
* Agent 2 gathers evidence only — it does not produce risk scores.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from ..agent1.output_schema import Agent1Output
from ...evidence.schemas import (
    CoreBankingResponse,
    KYCResponse,
    DeviceRegistryResponse,
    BeneficiaryResponse,
    SanctionsResponse,
    GeolocationResponse,
    NewsResponse,
    EvidenceStatus,
)


# ---------------------------------------------------------------------------
# Agent 2 status
# ---------------------------------------------------------------------------

class Agent2Status(str, Enum):
    """Overall status of the Agent 2 evidence gathering run."""

    COMPLETE = "COMPLETE"
    """All provider calls succeeded (may include NOT_FOUND / NO_MATCH results)."""

    PARTIAL = "PARTIAL"
    """Some providers failed or timed out; evidence is incomplete."""

    FAILED = "FAILED"
    """Critical failure: required inputs were invalid or all providers failed."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    """Invalid or missing required inputs before any evidence was gathered."""


# ---------------------------------------------------------------------------
# Evidence result wrapper
# ---------------------------------------------------------------------------

class ProviderResult(BaseModel):
    """Wrapper tracking the outcome of a single provider call."""

    model_config = ConfigDict(frozen=True)

    provider_name: str = Field(description="Identifier for the evidence provider.")
    status: EvidenceStatus = Field(description="Outcome status from the provider.")
    retrieved_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when the evidence was retrieved.",
    )
    error_summary: Optional[str] = Field(
        default=None,
        description=(
            "Short sanitized error description when status is PROVIDER_ERROR "
            "or AUTH_ERROR. Does not contain stack traces or credentials."
        ),
    )
    timed_out: bool = Field(
        default=False,
        description="True when the provider call was cancelled due to a timeout.",
    )

    @property
    def succeeded(self) -> bool:
        """True when the provider returned a usable evidence response."""
        return self.status in (
            EvidenceStatus.FOUND,
            EvidenceStatus.NO_MATCH,
            EvidenceStatus.MATCH_FOUND,
            EvidenceStatus.NO_ARTICLES,
            EvidenceStatus.NOT_FOUND,
        )


# ---------------------------------------------------------------------------
# Agent 2 output
# ---------------------------------------------------------------------------

class Agent2Output(BaseModel):
    """Structured output for Agent 2 (Evidence Gatherer).

    Contains all evidence gathered from the seven provider categories,
    structured by category. Failed providers are preserved as ProviderResult
    entries with error_summary populated.

    Downstream agents (Risk Assessor, Explanation Generator) must:
    - Check `status` and `failed_providers` before consuming evidence.
    - Not treat missing evidence as a safe/clean finding.
    - Not fabricate evidence for failed providers.
    """

    model_config = ConfigDict(frozen=True)

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    agent2_run_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this Agent 2 run.",
    )
    transaction_id: Optional[str] = Field(
        default=None,
        description="raw_record_id from the CanonicalTransaction.",
    )
    source_dataset: Optional[str] = Field(
        default=None,
        description="source_dataset from the CanonicalTransaction.",
    )
    gathered_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when Agent 2 completed evidence gathering.",
    )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    status: Agent2Status = Field(
        description="Overall evidence gathering status."
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings (partial failures, missing identifiers, etc.).",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Error messages. Non-empty when status is FAILED.",
    )

    # ------------------------------------------------------------------
    # Agent 1 linkage (passed through; not modified)
    # ------------------------------------------------------------------
    agent1_output: Optional[Agent1Output] = Field(
        default=None,
        description=(
            "The Agent 1 output that triggered this evidence run. "
            "Preserved unchanged. Agent 2 does NOT modify anomaly scores."
        ),
    )

    # ------------------------------------------------------------------
    # Evidence results by provider category
    # ------------------------------------------------------------------
    core_banking: Optional[CoreBankingResponse] = Field(
        default=None,
        description="Sender account transaction history and statistics.",
    )
    kyc: Optional[KYCResponse] = Field(
        default=None,
        description="KYC customer profile for the sender account.",
    )
    device: Optional[DeviceRegistryResponse] = Field(
        default=None,
        description="Device registration status.",
    )
    beneficiary: Optional[BeneficiaryResponse] = Field(
        default=None,
        description="Beneficiary account profile.",
    )
    sanctions_subject: Optional[SanctionsResponse] = Field(
        default=None,
        description="Sanctions screening by customer name (when available).",
    )
    sanctions_account: Optional[SanctionsResponse] = Field(
        default=None,
        description="Sanctions screening by account ID.",
    )
    geolocation: Optional[GeolocationResponse] = Field(
        default=None,
        description="Transaction location vs registered location analysis.",
    )
    news: Optional[NewsResponse] = Field(
        default=None,
        description="News search results for the entity.",
    )

    # ------------------------------------------------------------------
    # Provider tracking
    # ------------------------------------------------------------------
    provider_results: list[ProviderResult] = Field(
        default_factory=list,
        description=(
            "Outcome summary for each provider call, including failures. "
            "Use this to identify evidence gaps."
        ),
    )
    failed_providers: list[str] = Field(
        default_factory=list,
        description="Names of providers that failed or timed out.",
    )
    successful_providers: list[str] = Field(
        default_factory=list,
        description="Names of providers that returned usable evidence.",
    )

    # ------------------------------------------------------------------
    # Evidence integrity note
    # ------------------------------------------------------------------
    evidence_note: str = Field(
        default=(
            "Agent 2 gathers evidence only. It does not produce risk scores. "
            "Missing evidence must not be interpreted as a safe or clean finding. "
            "Provider failures are preserved in failed_providers and provider_results. "
            "Sanctions failures are NOT equivalent to a clean sanctions result."
        ),
        description="Documents evidence gathering semantics and limitations.",
    )
