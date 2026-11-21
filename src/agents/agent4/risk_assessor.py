"""
Sentinel AI — Agent 4: Risk Assessor

Deterministically combines Agent 1–3 outputs into a risk score, score
breakdown, recommended action, confidence, SAR/STR recommendation and
regulatory matches.

Algorithm
---------
1. Extract the seven signals (signals.py). Each is a value in [0, 1] or
   UNAVAILABLE.
2. evidence_coverage = Σ weight of available signals.
   risk_score = 100 × Σ(weight × value over available) / evidence_coverage
   (renormalised over available evidence; missing evidence lowers coverage
   and confidence — it is never scored as safe).
3. score_band_action = band of risk_score (config thresholds).
4. Overrides raise the action to a minimum severity:
     OVR-SANCTIONS-MATCH        → BLOCK         (sanctions MATCH_FOUND)
     OVR-SANCTIONS-UNAVAILABLE  → HUMAN_REVIEW  (screen failed / not completed)
     OVR-LOW-COVERAGE           → HUMAN_REVIEW  (coverage < min_evidence_coverage)
   recommended_action = most severe of band action and all overrides.
5. SAR/STR recommended when recommended_action ≥ sar_min_action.
6. Regulatory triggers are derived from signals, KYC evidence and Agent 3
   pattern types, then resolved ONLY against the approved mapping registry.

No LLM is involved. Identical inputs and configuration always produce an
identical assessment (apart from run id and timestamp).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ...schemas.canonical_transaction import CanonicalTransaction
from .config import (
    ACTION_SEVERITY,
    Agent4Config,
    RecommendedAction,
    RiskSignal,
    more_severe,
)
from .output_schema import (
    Agent4Output,
    Agent4Status,
    AppliedOverride,
    ConfidenceLevel,
    RegulatoryMatch,
    SARRecommendation,
    SignalContribution,
)
from .regulatory_mapping import (
    MAPPING_VERSION,
    RegulatoryTrigger,
    get_reference,
    mappings_for,
)
from .signals import (
    enum_str,
    SignalResult,
    extract_anomaly,
    extract_location,
    extract_network_risk,
    extract_new_beneficiary,
    extract_new_device,
    extract_sanctions,
    extract_unusual_timing,
)

logger = logging.getLogger(__name__)

# Signals whose positive value raises a same-named regulatory trigger.
_SIGNAL_TRIGGERS: dict[RiskSignal, RegulatoryTrigger] = {
    RiskSignal.ANOMALY: RegulatoryTrigger.UNUSUAL_TRANSACTION,
    RiskSignal.NEW_DEVICE: RegulatoryTrigger.NEW_DEVICE,
    RiskSignal.NEW_BENEFICIARY: RegulatoryTrigger.NEW_BENEFICIARY,
    RiskSignal.UNUSUAL_TIMING: RegulatoryTrigger.UNUSUAL_TIMING,
    RiskSignal.LOCATION_ANOMALY: RegulatoryTrigger.LOCATION_ANOMALY,
}


def _status_str(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    return enum_str(getattr(obj, "status", None))


class RiskAssessorAgent:
    """
    Agent 4: Risk Assessor.

    Example
    -------
    ::

        agent = RiskAssessorAgent()
        state = agent({"transaction": tx, "agent1_output": a1,
                       "agent2_output": a2, "agent3_output": a3})
        output = state["agent4_output"]
    """

    def __init__(self, config: Optional[Agent4Config] = None) -> None:
        self._config = config or Agent4Config()

    @property
    def config(self) -> Agent4Config:
        return self._config

    # ------------------------------------------------------------------
    # LangGraph-compatible node
    # ------------------------------------------------------------------

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        transaction = state.get("transaction")
        agent2 = state.get("agent2_output")
        agent1 = state.get("agent1_output")
        if agent1 is None and agent2 is not None:
            agent1 = getattr(agent2, "agent1_output", None)
        output = self.assess(
            transaction=transaction,
            agent1_output=agent1,
            agent2_output=agent2,
            agent3_output=state.get("agent3_output"),
        )
        return {**state, "agent4_output": output}

    # ------------------------------------------------------------------
    # Main assessment
    # ------------------------------------------------------------------

    def assess(
        self,
        transaction: Optional[CanonicalTransaction],
        agent1_output: Any = None,
        agent2_output: Any = None,
        agent3_output: Any = None,
    ) -> Agent4Output:
        cfg = self._config
        if transaction is None:
            return self._validation_error("No transaction provided in pipeline state.")

        try:
            return self._assess(transaction, agent1_output, agent2_output, agent3_output)
        except Exception as exc:  # defensive: never crash the pipeline
            logger.exception("Agent 4 assessment failed")
            return Agent4Output(
                transaction_id=transaction.raw_record_id,
                source_dataset=enum_str(transaction.source_dataset),
                status=Agent4Status.FAILED,
                errors=[f"Risk assessment failed: {type(exc).__name__}"],
                recommended_action=RecommendedAction.HUMAN_REVIEW,
                confidence=ConfidenceLevel.LOW,
                confidence_reasons=["Assessment failed; manual review required."],
                sar_recommendation=SARRecommendation(recommended=False),
                mapping_version=MAPPING_VERSION,
                config_version=cfg.config_version,
                config_approval_status=cfg.approval_status,
                config_snapshot=cfg.as_audit_dict(),
            )

    def _assess(self, tx, agent1, agent2, agent3) -> Agent4Output:
        cfg = self._config
        sanctions = extract_sanctions(agent2)
        results: dict[RiskSignal, SignalResult] = {
            RiskSignal.ANOMALY: extract_anomaly(agent1),
            RiskSignal.NEW_DEVICE: extract_new_device(tx, agent2),
            RiskSignal.NEW_BENEFICIARY: extract_new_beneficiary(tx, agent2, cfg),
            RiskSignal.UNUSUAL_TIMING: extract_unusual_timing(tx, cfg),
            RiskSignal.NETWORK_RISK: extract_network_risk(agent3, cfg),
            RiskSignal.SANCTIONS_HIT: sanctions.result,
            RiskSignal.LOCATION_ANOMALY: extract_location(agent2),
        }

        # ---- score ---------------------------------------------------
        breakdown: list[SignalContribution] = []
        warnings: list[str] = []
        coverage = 0.0
        weighted = 0.0
        for sig in RiskSignal:
            r = results[sig]
            w = cfg.weights[sig]
            contrib = w * r.value if r.available else 0.0
            if r.available:
                coverage += w
                weighted += contrib
            breakdown.append(SignalContribution(
                signal=sig, weight=w, available=r.available, value=r.value,
                contribution=round(contrib, 6), rationale=r.rationale,
                evidence_refs=r.evidence_refs,
            ))
            warnings.extend(r.warnings)

        coverage = round(min(coverage, 1.0), 6)
        unavailable = [s for s in RiskSignal if not results[s].available]

        if coverage <= 0.0:
            risk_score = None
            band_action = None
            status = Agent4Status.FAILED
        else:
            risk_score = round(100.0 * weighted / coverage, 2)
            band_action = cfg.action_for_score(risk_score)
            status = Agent4Status.COMPLETE if not unavailable else Agent4Status.PARTIAL

        if unavailable:
            warnings.append(
                "Unavailable signals (not scored as safe): "
                + ", ".join(s.value for s in unavailable)
            )

        # ---- overrides -----------------------------------------------
        overrides: list[AppliedOverride] = []
        if sanctions.match_found and cfg.sanctions_match_forces_block:
            overrides.append(AppliedOverride(
                rule_id="OVR-SANCTIONS-MATCH",
                description="Sanctions screening returned a match; transaction must be blocked pending review.",
                minimum_action=RecommendedAction.BLOCK))
        if sanctions.screening_failed and cfg.sanctions_unavailable_forces_review:
            overrides.append(AppliedOverride(
                rule_id="OVR-SANCTIONS-UNAVAILABLE",
                description="Sanctions screening failed or did not complete; a failed screen is not a clean result.",
                minimum_action=RecommendedAction.HUMAN_REVIEW))
        if coverage < cfg.min_evidence_coverage:
            overrides.append(AppliedOverride(
                rule_id="OVR-LOW-COVERAGE",
                description=(f"Evidence coverage {coverage:.2f} below minimum "
                             f"{cfg.min_evidence_coverage:.2f}; score alone cannot clear the case."),
                minimum_action=RecommendedAction.HUMAN_REVIEW))

        action = band_action or RecommendedAction.HUMAN_REVIEW
        for o in overrides:
            action = more_severe(action, o.minimum_action)

        # ---- confidence ----------------------------------------------
        confidence, conf_reasons = self._confidence(coverage, agent1, agent2, agent3)

        # ---- SAR -----------------------------------------------------
        sar_basis: list[str] = []
        if ACTION_SEVERITY[action] >= ACTION_SEVERITY[cfg.sar_min_action]:
            if band_action is not None and ACTION_SEVERITY[band_action] >= ACTION_SEVERITY[cfg.sar_min_action]:
                sar_basis.append(f"SCORE_BAND_{band_action.value} (risk_score={risk_score})")
            sar_basis.extend(o.rule_id for o in overrides
                             if ACTION_SEVERITY[o.minimum_action] >= ACTION_SEVERITY[cfg.sar_min_action])
        sar = SARRecommendation(recommended=bool(sar_basis), basis=sar_basis)

        # ---- regulatory ----------------------------------------------
        triggers = self._triggers(results, sanctions.match_found, agent2, agent3, sar.recommended)
        matches, unmapped = self._resolve_mappings(triggers, tx.raw_record_id)

        return Agent4Output(
            transaction_id=tx.raw_record_id,
            source_dataset=enum_str(tx.source_dataset),
            status=status,
            warnings=warnings,
            errors=["No risk signal was available; no score produced."] if status == Agent4Status.FAILED else [],
            risk_score=risk_score,
            score_band_action=band_action,
            score_breakdown=breakdown,
            evidence_coverage=coverage,
            unavailable_signals=unavailable,
            recommended_action=action,
            overrides_applied=overrides,
            confidence=confidence,
            confidence_reasons=conf_reasons,
            sar_recommendation=sar,
            regulatory_matches=matches,
            unmapped_triggers=unmapped,
            mapping_version=MAPPING_VERSION,
            config_version=cfg.config_version,
            config_approval_status=cfg.approval_status,
            config_snapshot=cfg.as_audit_dict(),
            agent1_status=_status_str(agent1),
            agent2_run_id=getattr(agent2, "agent2_run_id", None),
            agent2_status=_status_str(agent2),
            agent3_run_id=getattr(agent3, "agent3_run_id", None),
            agent3_status=_status_str(agent3),
        )

    # ------------------------------------------------------------------

    def _confidence(self, coverage, agent1, agent2, agent3):
        cfg = self._config
        reasons = [f"evidence_coverage={coverage:.2f}"]
        degraded = []
        for name, out, ok in (("Agent 1", agent1, {"COMPLETE"}),
                              ("Agent 2", agent2, {"COMPLETE"}),
                              ("Agent 3", agent3, {"COMPLETE"})):
            st = _status_str(out)
            if st is None:
                degraded.append(f"{name} output missing")
            elif st not in ok:
                degraded.append(f"{name} status {st}")
        reasons.extend(degraded)

        if coverage < cfg.min_evidence_coverage:
            return ConfidenceLevel.LOW, reasons
        if coverage >= cfg.high_confidence_coverage and not degraded:
            return ConfidenceLevel.HIGH, reasons
        return ConfidenceLevel.MEDIUM, reasons

    def _triggers(self, results, sanctions_match, agent2, agent3, sar_recommended):
        cfg = self._config
        found: list[tuple[RegulatoryTrigger, str]] = []

        if sanctions_match:
            found.append((RegulatoryTrigger.SANCTIONS_MATCH,
                          results[RiskSignal.SANCTIONS_HIT].rationale))
        for sig, trig in _SIGNAL_TRIGGERS.items():
            r = results[sig]
            if r.available and r.value >= cfg.trigger_threshold:
                found.append((trig, r.rationale))

        kyc = getattr(agent2, "kyc", None) if agent2 is not None else None
        if kyc is not None and getattr(kyc, "data", None) is not None:
            if kyc.data.kyc_status != "VERIFIED":
                found.append((RegulatoryTrigger.KYC_NOT_VERIFIED,
                              f"sender KYC status {kyc.data.kyc_status}"))
            if kyc.data.pep:
                found.append((RegulatoryTrigger.PEP_INVOLVED, "KYC record: pep=True"))

        if agent3 is not None:
            seen = set()
            for f in getattr(agent3, "findings", []) or []:
                pt = enum_str(f.pattern_type)
                if pt in seen:
                    continue
                seen.add(pt)
                found.append((RegulatoryTrigger(pt),
                              f"Agent 3 {pt} finding {f.finding_id} on {f.subject_account_id}"))

        if sar_recommended:
            found.append((RegulatoryTrigger.SAR_RECOMMENDED, "SAR/STR recommended by action rules"))
        return found

    @staticmethod
    def _resolve_mappings(triggers, transaction_id):
        matches: list[RegulatoryMatch] = []
        unmapped: list[RegulatoryTrigger] = []
        for trig, detail in triggers:
            entries = mappings_for(trig)
            if not entries:
                if trig not in unmapped:
                    unmapped.append(trig)
                continue
            for m in entries:
                ref = get_reference(m.reference_id)
                matches.append(RegulatoryMatch(
                    mapping_id=m.mapping_id,
                    trigger=trig,
                    detected_pattern_detail=detail,
                    reference_id=ref.reference_id,
                    organization=ref.organization,
                    document_name=ref.document_name,
                    document_version=ref.document_version,
                    section=ref.section,
                    pdf_page=ref.pdf_page,
                    excerpt=ref.excerpt,
                    source_file=ref.source_file,
                    mapping_rationale=m.rationale,
                    verification_status=ref.verification_status,
                    caveats=list(ref.caveats),
                    case_transaction_id=transaction_id,
                ))
        return matches, unmapped

    def _validation_error(self, msg: str) -> Agent4Output:
        cfg = self._config
        return Agent4Output(
            status=Agent4Status.VALIDATION_ERROR,
            errors=[msg],
            recommended_action=RecommendedAction.HUMAN_REVIEW,
            confidence=ConfidenceLevel.LOW,
            confidence_reasons=["Invalid input; nothing assessed."],
            sar_recommendation=SARRecommendation(recommended=False),
            mapping_version=MAPPING_VERSION,
            config_version=cfg.config_version,
            config_approval_status=cfg.approval_status,
            config_snapshot=cfg.as_audit_dict(),
        )
