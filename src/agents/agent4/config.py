"""
Sentinel AI — Agent 4: Risk Assessor Configuration

Every number that influences the final risk score, the recommended action,
or the SAR/STR recommendation lives here — never inside an LLM prompt and
never scattered through the scoring code.

APPROVAL STATUS: PROPOSED
-------------------------
The project plan states that a weighted scoring model exists but the actual
weights, action bands and override rules were never recorded in the
repository. The values below are PROPOSED DEFAULTS written on 2026-11-21 so
that Phase 9 could be built. They are engineering judgements for a synthetic
prototype and MUST be reviewed and approved by the project team before being
presented as the project's scoring policy. Every Agent 4 output carries
`config_version` and `config_approval_status` so an unapproved configuration
can never be mistaken for an approved one.

Design rules
------------
* Weights are explicit, sum to 1.0 and are validated at construction.
* Action bands are explicit, ascending, and validated at construction.
* Override rules are explicit booleans with documented semantics.
* The configuration is frozen; a change requires a new instance (and, for the
  project default, a new `config_version`).
* No value here is a regulatory threshold or a legal determination.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Optional


class RiskSignal(str, Enum):
    """The seven risk signals defined by the project plan."""

    ANOMALY = "ANOMALY"
    """Agent 1 ML anomaly result (combined_confidence, else XGBoost probability)."""

    NEW_DEVICE = "NEW_DEVICE"
    """Transaction initiated from a device not registered to the sender account."""

    NEW_BENEFICIARY = "NEW_BENEFICIARY"
    """Payment to a beneficiary with no prior relationship, or one previously flagged."""

    UNUSUAL_TIMING = "UNUSUAL_TIMING"
    """Transaction at night (local time) or very soon after the beneficiary was added."""

    NETWORK_RISK = "NETWORK_RISK"
    """Agent 3 network-pattern findings (max heuristic score)."""

    SANCTIONS_HIT = "SANCTIONS_HIT"
    """Sanctions screening returned a match for the subject or account."""

    LOCATION_ANOMALY = "LOCATION_ANOMALY"
    """Transaction location far from the registered location."""


class RecommendedAction(str, Enum):
    """Recommended actions, ordered by severity (see ACTION_SEVERITY)."""

    CLEAR = "CLEAR"
    MONITOR = "MONITOR"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    ESCALATE = "ESCALATE"
    BLOCK = "BLOCK"


ACTION_SEVERITY: Mapping[RecommendedAction, int] = MappingProxyType({
    RecommendedAction.CLEAR: 0,
    RecommendedAction.MONITOR: 1,
    RecommendedAction.HUMAN_REVIEW: 2,
    RecommendedAction.ESCALATE: 3,
    RecommendedAction.BLOCK: 4,
})


def more_severe(a: RecommendedAction, b: RecommendedAction) -> RecommendedAction:
    """Return the more severe of two actions."""
    return a if ACTION_SEVERITY[a] >= ACTION_SEVERITY[b] else b


# ---------------------------------------------------------------------------
# Proposed default weights
# ---------------------------------------------------------------------------
# Rationale (PROPOSED — pending approval):
#   ANOMALY 0.30          Strongest measured signal (XGBoost ROC-AUC 0.934).
#   NETWORK_RISK 0.20     Seven graph detectors; captures layering/mule typologies
#                         that single-transaction models cannot see.
#   SANCTIONS_HIT 0.15    Also enforced by a hard override (BLOCK), so its
#                         weight only shapes the score, not the decision.
#   NEW_BENEFICIARY 0.10  Classic authorised-push-payment / mule indicator.
#   NEW_DEVICE 0.10       Account-takeover indicator.
#   LOCATION_ANOMALY 0.10 Account-takeover / travel indicator; noisier.
#   UNUSUAL_TIMING 0.05   Weakest standalone signal; many legitimate night txns.
_DEFAULT_WEIGHTS: dict[RiskSignal, float] = {
    RiskSignal.ANOMALY: 0.30,
    RiskSignal.NETWORK_RISK: 0.20,
    RiskSignal.SANCTIONS_HIT: 0.15,
    RiskSignal.NEW_BENEFICIARY: 0.10,
    RiskSignal.NEW_DEVICE: 0.10,
    RiskSignal.LOCATION_ANOMALY: 0.10,
    RiskSignal.UNUSUAL_TIMING: 0.05,
}


@dataclass(frozen=True)
class Agent4Config:
    """
    Scoring configuration for Agent 4.

    Parameters
    ----------
    weights:
        Weight per RiskSignal. Must cover all seven signals, each in [0, 1],
        summing to 1.0.

    monitor_threshold, escalate_threshold, block_threshold:
        Action bands on the 0–100 risk score:
            score <  monitor_threshold   → CLEAR
            score <  escalate_threshold  → MONITOR
            score <  block_threshold     → ESCALATE
            score >= block_threshold     → BLOCK
        Defaults: 25 / 50 / 75.

    min_evidence_coverage:
        Minimum fraction of total signal weight that must be AVAILABLE for
        the score to drive the action on its own. Below this, the action is
        raised to at least HUMAN_REVIEW, because missing evidence must never
        be treated as safe evidence. Default: 0.60.

    sanctions_match_forces_block:
        When True, any sanctions MATCH_FOUND forces BLOCK and a SAR/STR
        recommendation regardless of the score. Default: True.

    sanctions_unavailable_forces_review:
        When True, a failed / unavailable sanctions screen raises the action
        to at least HUMAN_REVIEW (a sanctions failure is not a clean result).
        Default: True.

    high_anomaly_review_threshold:
        When the ANOMALY signal is at or above this value, the action is
        raised to at least HUMAN_REVIEW (OVR-HIGH-ANOMALY). A model score on
        its own is not grounds for escalation or a SAR, but a strong one must
        not be left at MONITOR. ``None`` disables the rule. Default: 0.70
        (Phase 9.5 evaluation: 96% of high-value spikes, 0.3% of legitimate
        transactions).

    sar_min_action:
        A SAR/STR recommendation is produced when the final action is at
        least this severe. Default: ESCALATE.

    night_start_hour, night_end_hour:
        Local-time window (using the transaction timestamp's own UTC offset)
        regarded as unusual. Wraps midnight. Defaults: 23 → 6
        (i.e. 23:00–05:59). The synthetic India dataset places ~85% of
        transactions between 08:00 and 21:59.

    recent_beneficiary_minutes:
        A payment made within this many minutes of the beneficiary being
        added is treated as unusual timing. Default: 60.

    new_beneficiary_account_age_days:
        A beneficiary account younger than this is a partial (0.5)
        new-beneficiary signal. Default: 30.

    network_finding_default_score:
        Signal value used for an Agent 3 finding that carries no
        heuristic_score. Default: 0.5.

    trigger_threshold:
        A signal value at or above this raises its regulatory trigger
        (e.g. ANOMALY ≥ 0.5 → UNUSUAL_TRANSACTION). Default: 0.5.

    high_confidence_coverage:
        Evidence coverage required (with no degraded upstream agent) for
        HIGH confidence. Coverage ≥ min_evidence_coverage gives MEDIUM;
        below that, LOW. Default: 0.90.

    config_version, approval_status:
        Recorded on every output for auditability.
    """

    weights: Mapping[RiskSignal, float] = field(
        default_factory=lambda: MappingProxyType(dict(_DEFAULT_WEIGHTS))
    )
    monitor_threshold: float = 25.0
    escalate_threshold: float = 50.0
    block_threshold: float = 75.0
    min_evidence_coverage: float = 0.60
    sanctions_match_forces_block: bool = True
    sanctions_unavailable_forces_review: bool = True
    high_anomaly_review_threshold: Optional[float] = 0.70
    sar_min_action: RecommendedAction = RecommendedAction.ESCALATE
    night_start_hour: int = 23
    night_end_hour: int = 6
    recent_beneficiary_minutes: int = 60
    new_beneficiary_account_age_days: int = 30
    network_finding_default_score: float = 0.5
    trigger_threshold: float = 0.5
    high_confidence_coverage: float = 0.90
    config_version: str = "1.0.0"
    approval_status: str = (
        "APPROVED 2026-11-21 (decision delegated by the project owner) — "
        "prototype policy calibrated on SYNTHETIC data; re-approve before use on real data"
    )

    def __post_init__(self) -> None:
        # Freeze a caller-supplied dict so the config stays immutable.
        if not isinstance(self.weights, MappingProxyType):
            object.__setattr__(self, "weights", MappingProxyType(dict(self.weights)))

        missing = set(RiskSignal) - set(self.weights)
        if missing:
            raise ValueError(
                f"weights must cover every RiskSignal; missing: "
                f"{sorted(s.value for s in missing)}"
            )
        extra = set(self.weights) - set(RiskSignal)
        if extra:
            raise ValueError(f"weights contain unknown signals: {extra}")
        for sig, w in self.weights.items():
            if not (0.0 <= w <= 1.0):
                raise ValueError(f"weight for {sig.value} must be in [0, 1]; got {w}")
        total = sum(self.weights.values())
        if not math.isclose(total, 1.0, abs_tol=1e-9):
            raise ValueError(f"weights must sum to 1.0; got {total}")

        if not (0.0 < self.monitor_threshold < self.escalate_threshold
                < self.block_threshold <= 100.0):
            raise ValueError(
                "action thresholds must satisfy "
                "0 < monitor < escalate < block <= 100; got "
                f"{self.monitor_threshold}/{self.escalate_threshold}/{self.block_threshold}"
            )
        if not (0.0 <= self.min_evidence_coverage <= 1.0):
            raise ValueError("min_evidence_coverage must be in [0, 1]")
        for name in ("night_start_hour", "night_end_hour"):
            if not (0 <= getattr(self, name) <= 23):
                raise ValueError(f"{name} must be in [0, 23]")
        if self.recent_beneficiary_minutes < 0:
            raise ValueError("recent_beneficiary_minutes must be >= 0")
        if self.new_beneficiary_account_age_days < 0:
            raise ValueError("new_beneficiary_account_age_days must be >= 0")
        for name in ("network_finding_default_score", "trigger_threshold",
                     "high_confidence_coverage"):
            if not (0.0 <= getattr(self, name) <= 1.0):
                raise ValueError(f"{name} must be in [0, 1]")
        if self.high_anomaly_review_threshold is not None and not (
            0.0 <= self.high_anomaly_review_threshold <= 1.0
        ):
            raise ValueError("high_anomaly_review_threshold must be in [0, 1] or None")
        if self.high_confidence_coverage < self.min_evidence_coverage:
            raise ValueError("high_confidence_coverage must be >= min_evidence_coverage")

    # ------------------------------------------------------------------

    def action_for_score(self, score: float) -> RecommendedAction:
        """Map a 0–100 risk score to its band action."""
        if score >= self.block_threshold:
            return RecommendedAction.BLOCK
        if score >= self.escalate_threshold:
            return RecommendedAction.ESCALATE
        if score >= self.monitor_threshold:
            return RecommendedAction.MONITOR
        return RecommendedAction.CLEAR

    def is_night_hour(self, hour: int) -> bool:
        """True if `hour` falls in the configured night window (wraps midnight)."""
        start, end = self.night_start_hour, self.night_end_hour
        if start == end:
            return False
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end

    def as_audit_dict(self) -> dict:
        """Plain-dict snapshot of the configuration for the audit trail."""
        return {
            "config_version": self.config_version,
            "approval_status": self.approval_status,
            "weights": {s.value: w for s, w in self.weights.items()},
            "monitor_threshold": self.monitor_threshold,
            "escalate_threshold": self.escalate_threshold,
            "block_threshold": self.block_threshold,
            "min_evidence_coverage": self.min_evidence_coverage,
            "sanctions_match_forces_block": self.sanctions_match_forces_block,
            "sanctions_unavailable_forces_review": self.sanctions_unavailable_forces_review,
            "high_anomaly_review_threshold": self.high_anomaly_review_threshold,
            "sar_min_action": self.sar_min_action.value,
            "night_start_hour": self.night_start_hour,
            "night_end_hour": self.night_end_hour,
            "recent_beneficiary_minutes": self.recent_beneficiary_minutes,
            "new_beneficiary_account_age_days": self.new_beneficiary_account_age_days,
            "network_finding_default_score": self.network_finding_default_score,
            "trigger_threshold": self.trigger_threshold,
            "high_confidence_coverage": self.high_confidence_coverage,
        }
