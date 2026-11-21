"""
Sentinel AI — Agent 4: Risk Assessor Output Schema

Design rules
------------
* The risk score is fully reproducible from `score_breakdown` + the recorded
  configuration: risk_score = 100 * Σ(contribution) / evidence_coverage.
* An unavailable signal is recorded with available=False and value=None. It
  is never scored as 0 ("safe"); it lowers `evidence_coverage` instead.
* Every action override is listed with its rule id.
* Regulatory matches come only from the approved registry
  (regulatory_mapping.py); triggers without an entry are listed in
  `unmapped_triggers`.
* A SAR/STR recommendation is a system recommendation requiring qualified
  human review. It is never a filing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .config import RecommendedAction, RiskSignal
from .regulatory_mapping import RegulatoryTrigger, VerificationStatus


class Agent4Status(str, Enum):
    COMPLETE = "COMPLETE"
    """All seven signals were available."""

    PARTIAL = "PARTIAL"
    """At least one signal was unavailable; score uses the available weight only."""

    FAILED = "FAILED"
    """No signal was available; no score could be produced."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    """Required inputs (transaction) were missing."""


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EvidenceRef(BaseModel):
    """Provenance pointer to the upstream evidence behind a signal."""

    model_config = ConfigDict(frozen=True)

    source_agent: str = Field(description="AGENT_1 / AGENT_2 / AGENT_3 / TRANSACTION.")
    source: str = Field(description="Provider / model / field that produced the value.")
    source_mode: Optional[str] = Field(default=None, description="MOCK or LIVE for Agent 2 evidence.")
    reference_id: Optional[str] = Field(default=None, description="request_id / finding_id / run id.")
    retrieved_at: Optional[str] = Field(default=None, description="UTC ISO-8601 timestamp.")
    detail: Optional[str] = None


class SignalContribution(BaseModel):
    """One row of the score breakdown."""

    model_config = ConfigDict(frozen=True)

    signal: RiskSignal
    weight: float
    available: bool
    value: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Normalised signal strength in [0, 1]; None when unavailable.",
    )
    contribution: float = Field(
        description="weight * value (0.0 when unavailable). Before renormalisation.",
    )
    rationale: str = Field(description="Plain-language reason for the value.")
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class AppliedOverride(BaseModel):
    """A deterministic rule that changed the band action."""

    model_config = ConfigDict(frozen=True)

    rule_id: str
    description: str
    minimum_action: RecommendedAction


class RegulatoryMatch(BaseModel):
    """A regulatory reference attached to this case (REGULATORY_MAPPING.md §Auditability)."""

    model_config = ConfigDict(frozen=True)

    mapping_id: str
    trigger: RegulatoryTrigger
    detected_pattern_detail: str
    reference_id: str
    organization: str
    document_name: str
    document_version: str
    section: str
    pdf_page: int
    excerpt: str
    source_file: str
    mapping_rationale: str
    verification_status: VerificationStatus
    caveats: list[str] = Field(default_factory=list)
    case_transaction_id: Optional[str] = None


class SARRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True)

    recommended: bool
    basis: list[str] = Field(default_factory=list, description="Rule ids / reasons.")
    note: str = (
        "SYSTEM RECOMMENDATION ONLY. This is not a regulatory filing. Any "
        "suspicious transaction report must be decided and filed by a "
        "qualified human reviewer."
    )


class Agent4Output(BaseModel):
    """Structured output for Agent 4 (Risk Assessor)."""

    model_config = ConfigDict(frozen=True)

    # Identity / provenance
    agent4_run_id: str = Field(default_factory=lambda: str(uuid4()))
    transaction_id: Optional[str] = None
    source_dataset: Optional[str] = None
    assessed_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Status
    status: Agent4Status
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    # Score
    risk_score: Optional[float] = Field(
        default=None, ge=0.0, le=100.0,
        description="0–100 deterministic risk score. None when status is FAILED/VALIDATION_ERROR.",
    )
    score_band_action: Optional[RecommendedAction] = Field(
        default=None, description="Action implied by the score band alone (before overrides).",
    )
    score_breakdown: list[SignalContribution] = Field(default_factory=list)
    evidence_coverage: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Sum of weights of AVAILABLE signals.",
    )
    unavailable_signals: list[RiskSignal] = Field(default_factory=list)

    # Decision
    recommended_action: RecommendedAction
    overrides_applied: list[AppliedOverride] = Field(default_factory=list)
    confidence: ConfidenceLevel
    confidence_reasons: list[str] = Field(default_factory=list)
    sar_recommendation: SARRecommendation

    # Regulatory
    regulatory_matches: list[RegulatoryMatch] = Field(default_factory=list)
    unmapped_triggers: list[RegulatoryTrigger] = Field(
        default_factory=list,
        description="Triggers present in this case with no approved mapping. Not invented.",
    )
    mapping_version: str

    # Configuration audit
    config_version: str
    config_approval_status: str
    config_snapshot: dict[str, Any] = Field(default_factory=dict)

    # Upstream linkage
    agent1_status: Optional[str] = None
    agent2_run_id: Optional[str] = None
    agent2_status: Optional[str] = None
    agent3_run_id: Optional[str] = None
    agent3_status: Optional[str] = None

    assessment_note: str = Field(
        default=(
            "Agent 4 produces a deterministic, configuration-driven risk score. "
            "It is NOT a calibrated fraud probability and NOT a legal or "
            "regulatory determination. Unavailable evidence is never scored as "
            "safe. Regulatory references come only from the approved mapping "
            "registry and are UNVERIFIED until reviewed by a qualified human. "
            "The recommended action requires analyst review."
        )
    )
