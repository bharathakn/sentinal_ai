"""
Sentinel AI — Phase 13: case record, alert, audit and analyst-decision schemas.

A case is created when an alert is ingested. It moves through:

    RECEIVED → INVESTIGATING → AWAITING_REVIEW → DECIDED
                             ↘ INVESTIGATION_FAILED

Case records are stored as JSON (``model_dump(mode="json")``) by every case
store, so the JSON-file and MongoDB stores hold identical documents.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..schemas.canonical_transaction import CanonicalTransaction

CASE_SCHEMA_VERSION = "1.0.0"

PROTOTYPE_NOTICE = (
    "PROTOTYPE — investigation of synthetic / public-dataset transactions with mock "
    "evidence providers. Not connected to banking infrastructure; not real customer data."
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CaseStatus(str, Enum):
    RECEIVED = "RECEIVED"
    INVESTIGATING = "INVESTIGATING"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    INVESTIGATION_FAILED = "INVESTIGATION_FAILED"
    DECIDED = "DECIDED"


#: Cases a restarted process must (re)queue: their investigation never finished.
UNFINISHED_STATUSES = (CaseStatus.RECEIVED, CaseStatus.INVESTIGATING)
#: Cases an analyst may decide (a decision may be revised; every one is kept).
DECIDABLE_STATUSES = (CaseStatus.AWAITING_REVIEW, CaseStatus.DECIDED)


class AlertSource(str, Enum):
    API = "API"                        # full transaction supplied by the caller
    SYNTHETIC_FEED = "SYNTHETIC_FEED"  # transaction looked up in the synthetic India dataset
    DATASET_RUN = "DATASET_RUN"        # selected by screening in a dataset run


class AnalystAction(str, Enum):
    """Analyst actions from the project plan (docs/10_FRONTEND/DASHBOARD.md)."""

    BLOCK = "BLOCK"
    MONITOR = "MONITOR"
    ESCALATE = "ESCALATE"
    CLEAR = "CLEAR"


#: Queue order: more severe recommended actions first.
ACTION_PRIORITY = {"BLOCK": 5, "ESCALATE": 4, "HUMAN_REVIEW": 3, "MONITOR": 2, "CLEAR": 1}


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class AlertRequest(BaseModel):
    """A suspicious-transaction alert. Give exactly one of ``transaction`` or
    ``transaction_id`` (a transaction from the synthetic India monitoring feed)."""

    model_config = ConfigDict(extra="forbid")

    transaction: Optional[CanonicalTransaction] = None
    transaction_id: Optional[str] = Field(default=None, min_length=1, max_length=64,
                                          pattern=r"^[A-Za-z0-9_\-]+$")
    alert_id: Optional[str] = Field(default=None, max_length=64)
    source_system: Optional[str] = Field(default=None, max_length=64,
                                         description="Name of the monitoring system that raised the alert.")

    @model_validator(mode="after")
    def _one_source(self) -> "AlertRequest":
        if (self.transaction is None) == (self.transaction_id is None):
            raise ValueError("Give exactly one of 'transaction' or 'transaction_id'.")
        return self


class DecisionRequest(BaseModel):
    """The analyst is the signed-in user; identity is never taken from the body."""

    model_config = ConfigDict(extra="forbid")

    action: AnalystAction
    rationale: str = Field(min_length=1, max_length=4000)


# ---------------------------------------------------------------------------
# Stored records
# ---------------------------------------------------------------------------

class AlertInfo(BaseModel):
    alert_id: Optional[str] = None
    source: AlertSource
    source_system: Optional[str] = None
    received_at_utc: datetime
    run_id: Optional[str] = None


class AuditEventType(str, Enum):
    CASE_CREATED = "CASE_CREATED"
    INVESTIGATION_STARTED = "INVESTIGATION_STARTED"
    INVESTIGATION_COMPLETED = "INVESTIGATION_COMPLETED"
    INVESTIGATION_FAILED = "INVESTIGATION_FAILED"
    INVESTIGATION_REQUEUED = "INVESTIGATION_REQUEUED"
    ANALYST_DECISION = "ANALYST_DECISION"


class AuditEvent(BaseModel):
    """Append-only audit entry."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: AuditEventType
    at_utc: datetime = Field(default_factory=utcnow)
    actor: str = Field(description="'system' or the analyst id.")
    details: dict[str, Any] = Field(default_factory=dict)


class AnalystDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: str(uuid4()))
    decided_at_utc: datetime = Field(default_factory=utcnow)
    analyst_id: str
    analyst_name: Optional[str] = None
    action: AnalystAction
    rationale: str
    # What the analyst was shown when deciding (audit context)
    system_recommended_action: Optional[str] = None
    system_risk_score: Optional[float] = None
    report_run_id: Optional[str] = None
    report_validation_status: Optional[str] = None
    agrees_with_system: Optional[bool] = None
    supersedes_decision_id: Optional[str] = None


class CaseSummary(BaseModel):
    """Queue fields, copied from the investigation outputs (never computed here)."""

    risk_score: Optional[float] = None
    recommended_action: Optional[str] = None
    score_band_action: Optional[str] = None
    confidence: Optional[str] = None
    sar_recommended: Optional[bool] = None
    report_generator: Optional[str] = None
    validation_status: Optional[str] = None
    pipeline_status: Optional[str] = None
    requires_human_review: bool = Field(
        default=True,
        description="True unless the report was VALIDATED and the pipeline COMPLETE. "
                    "Every case still needs an analyst decision.",
    )
    priority_rank: int = Field(default=0, description="ACTION_PRIORITY of the recommended action; 0 = none yet.")


class CaseRecord(BaseModel):
    schema_version: str = CASE_SCHEMA_VERSION
    case_id: str
    transaction_key: str = Field(description="source_dataset:raw_record_id — de-duplicates repeated alerts.")
    status: CaseStatus
    created_at_utc: datetime
    updated_at_utc: datetime
    prototype_notice: str = PROTOTYPE_NOTICE
    alert: AlertInfo
    transaction: dict[str, Any] = Field(description="Canonical transaction with ground-truth labels removed.")
    summary: CaseSummary = Field(default_factory=CaseSummary)
    investigation: Optional[dict[str, Any]] = Field(
        default=None, description="Pipeline outputs (agent1_output … validation_output, pipeline_trace).")
    investigation_error: Optional[str] = None
    analyst_decision: Optional[AnalystDecision] = None
    decisions: list[AnalystDecision] = Field(default_factory=list)
    audit_trail: list[AuditEvent] = Field(default_factory=list)


class CaseListItem(BaseModel):
    case_id: str
    status: CaseStatus
    created_at_utc: datetime
    updated_at_utc: datetime
    transaction_id: Optional[str] = None
    amount: Optional[str] = None
    currency: Optional[str] = None
    alert: AlertInfo
    summary: CaseSummary
    analyst_action: Optional[AnalystAction] = None


class CaseList(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[CaseListItem]
    prototype_notice: str = PROTOTYPE_NOTICE


class AlertAccepted(BaseModel):
    case_id: str
    status: CaseStatus
    duplicate: bool = Field(description="True when an existing case for the same transaction was returned.")
    summary: Optional[CaseSummary] = None
