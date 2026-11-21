"""
Sentinel AI — Output Validator (Phase 11)

Deterministic validation of Agent 5 reports against the evidence bundle, the
case state and the Risk Assessor. Result: VALIDATED or NEEDS_HUMAN_REVIEW
with per-check results. No LLM is used.
"""

from .output_validator import OutputValidator, validate_report
from .schema import (
    CHECK_DESCRIPTIONS,
    VALIDATOR_VERSION,
    CheckId,
    CheckResult,
    ReportReviewRecord,
    StatementIssue,
    ValidationOutput,
    ValidationStatus,
)
from .stage import ValidationStage

__all__ = [
    "OutputValidator",
    "ValidationStage",
    "validate_report",
    "CHECK_DESCRIPTIONS",
    "VALIDATOR_VERSION",
    "CheckId",
    "CheckResult",
    "ReportReviewRecord",
    "StatementIssue",
    "ValidationOutput",
    "ValidationStatus",
]
