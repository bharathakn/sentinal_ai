"""
Sentinel AI — Output Validator: result schema.

Validation is deterministic. A report is VALIDATED only when every check
passes; otherwise NEEDS_HUMAN_REVIEW, and the per-check results explain why.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from ..agent5.report_schema import Agent5Output

VALIDATOR_VERSION = "1.0.0"


class ValidationStatus(str, Enum):
    VALIDATED = "VALIDATED"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"


class CheckId(str, Enum):
    STRUCTURE = "STRUCTURE"
    BUNDLE_INTEGRITY = "BUNDLE_INTEGRITY"
    CITATION_GROUNDING = "CITATION_GROUNDING"
    DECISION_CONSISTENCY = "DECISION_CONSISTENCY"
    REGULATORY = "REGULATORY"
    LANGUAGE = "LANGUAGE"
    LABEL_LEAKAGE = "LABEL_LEAKAGE"


CHECK_DESCRIPTIONS: dict[CheckId, str] = {
    CheckId.STRUCTURE: "Seven sections in order, non-empty; every statement cites existing facts; "
                       "no upstream output missing.",
    CheckId.BUNDLE_INTEGRITY: "Evidence bundle hash recomputes, the bundle equals a fresh rebuild from the "
                              "case state, every fact has a source, the audit trail cites every fact.",
    CheckId.CITATION_GROUNDING: "Every identifier, date, time and number in a statement appears in a fact "
                                "the statement cites.",
    CheckId.DECISION_CONSISTENCY: "Decision equals the Risk Assessor output; the decision statement matches; "
                                  "narrative action names and SAR/STR wording agree with it.",
    CheckId.REGULATORY: "Regulatory references are exactly the Risk Assessor's approved matches; the "
                        "narrative names no regulation or regulator.",
    CheckId.LANGUAGE: "The narrative contains no conclusive or accusatory wording.",
    CheckId.LABEL_LEAKAGE: "No dataset ground-truth label appears in the report or its evidence.",
}


class StatementIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    check: CheckId
    section: Optional[str] = None
    statement_index: Optional[int] = None  # 0-based within the section
    origin: Optional[str] = None
    text: Optional[str] = None
    reason: str


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    check: CheckId
    description: str
    passed: bool
    items_checked: int = 0
    issues: list[StatementIssue] = Field(default_factory=list)


class ValidationOutput(BaseModel):
    """Result of validating one Agent 5 report."""

    model_config = ConfigDict(frozen=True)

    validation_run_id: str = Field(default_factory=lambda: str(uuid4()))
    validator_version: str = VALIDATOR_VERSION
    validated_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    case_id: Optional[str] = None
    transaction_id: Optional[str] = None
    report_run_id: Optional[str] = Field(default=None, description="agent5_run_id of the validated report.")
    report_generator: Optional[str] = None
    bundle_hash: Optional[str] = None

    status: ValidationStatus
    checks: list[CheckResult] = Field(default_factory=list)
    checks_passed: int = 0
    checks_total: int = 0
    analyst_warning: Optional[str] = None

    def failed_checks(self) -> list[CheckId]:
        return [c.check for c in self.checks if not c.passed]

    def check(self, check_id: CheckId) -> Optional[CheckResult]:
        return next((c for c in self.checks if c.check == check_id), None)


class ReportReviewRecord(BaseModel):
    """A report that was generated but not presented, kept for audit."""

    model_config = ConfigDict(frozen=True)

    reason: str
    report: Agent5Output
    validation: ValidationOutput
