"""
Sentinel AI — Agent 4: Signal extraction

Converts upstream structured outputs (transaction, Agent 1, Agent 2,
Agent 3) into the seven normalised risk signals.

Rules
-----
* Each extractor returns a SignalResult: value in [0, 1] or None
  (unavailable), a plain-language rationale, and provenance refs.
* When several independent indicators exist for one signal, the signal
  value is the MAX of the available indicators (the strongest evidence wins;
  one clean indicator cannot mask a positive one).
* Missing, failed or errored evidence yields no indicator. If no indicator
  is available the signal is UNAVAILABLE — never 0.0.
* Extractors only read; they never modify upstream outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from ...evidence.schemas import EvidenceResponse, EvidenceStatus
from ...schemas.canonical_transaction import CanonicalTransaction
from .config import Agent4Config, RiskSignal
from .output_schema import EvidenceRef


@dataclass
class SignalResult:
    signal: RiskSignal
    value: Optional[float]
    rationale: str
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return self.value is not None


@dataclass
class _Indicator:
    value: float
    reason: str
    ref: EvidenceRef


def enum_str(value: Any) -> Optional[str]:
    """Enum or plain string → string (CanonicalTransaction uses use_enum_values)."""
    if value is None:
        return None
    return getattr(value, "value", str(value))


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt is not None else None


def _evidence_ref(resp: EvidenceResponse, detail: Optional[str] = None) -> EvidenceRef:
    return EvidenceRef(
        source_agent="AGENT_2",
        source=resp.source,
        source_mode=resp.source_mode.value,
        reference_id=resp.request_id,
        retrieved_at=_iso(resp.retrieved_at),
        detail=detail,
    )


def _tx_ref(tx: CanonicalTransaction, field_name: str) -> EvidenceRef:
    return EvidenceRef(
        source_agent="TRANSACTION",
        source=f"CanonicalTransaction.{field_name}",
        reference_id=tx.raw_record_id,
        detail=f"source_dataset={enum_str(tx.source_dataset)}",
    )


def _combine(signal: RiskSignal, indicators: list[_Indicator],
             unavailable_reason: str) -> SignalResult:
    if not indicators:
        return SignalResult(signal=signal, value=None, rationale=unavailable_reason)
    value = max(i.value for i in indicators)
    rationale = "; ".join(i.reason for i in indicators)
    return SignalResult(
        signal=signal,
        value=value,
        rationale=rationale,
        evidence_refs=[i.ref for i in indicators],
    )


def _found(resp: Optional[EvidenceResponse]) -> bool:
    return resp is not None and resp.status == EvidenceStatus.FOUND and getattr(resp, "data", None) is not None


# ---------------------------------------------------------------------------
# ANOMALY (Agent 1)
# ---------------------------------------------------------------------------

_A1_UNUSABLE = {"FAILED", "VALIDATION_ERROR"}
_A1_DEGRADED = {"PARTIAL", "COMPATIBILITY_WARNING"}


def extract_anomaly(agent1: Any) -> SignalResult:
    sig = RiskSignal.ANOMALY
    if agent1 is None:
        return SignalResult(sig, None, "Agent 1 output not available.")
    status = getattr(agent1.status, "value", str(agent1.status))
    if status in _A1_UNUSABLE:
        return SignalResult(sig, None, f"Agent 1 status {status}; no usable anomaly score.")

    if agent1.combined_confidence is not None:
        value, src = float(agent1.combined_confidence), "combined_confidence"
        reason = (f"Agent 1 combined_confidence={value:.3f} "
                  "(heuristic 70/30 XGBoost/IF composite, not a probability)")
    elif agent1.anomaly_score is not None:
        value, src = float(agent1.anomaly_score), "anomaly_score (XGBoost)"
        reason = (f"Agent 1 XGBoost anomaly_score={value:.3f} "
                  "(combined_confidence unavailable)")
    else:
        return SignalResult(sig, None, f"Agent 1 status {status} but no score present.")

    value = min(max(value, 0.0), 1.0)
    warnings = []
    if status in _A1_DEGRADED:
        warnings.append(f"Agent 1 status {status}: anomaly signal is degraded.")
        reason += f"; Agent 1 status {status}"
    return SignalResult(
        signal=sig, value=value, rationale=reason,
        evidence_refs=[EvidenceRef(
            source_agent="AGENT_1", source=src,
            reference_id=agent1.transaction_id,
            retrieved_at=_iso(agent1.scored_at_utc),
        )],
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# NEW_DEVICE
# ---------------------------------------------------------------------------

def extract_new_device(tx: CanonicalTransaction, agent2: Any) -> SignalResult:
    ind: list[_Indicator] = []
    flag = tx.device.is_new_device if tx.device else None
    if flag is not None:
        ind.append(_Indicator(
            1.0 if flag else 0.0,
            f"transaction flags is_new_device={flag}",
            _tx_ref(tx, "device.is_new_device"),
        ))

    dev = getattr(agent2, "device", None) if agent2 is not None else None
    if _found(dev):
        d = dev.data
        registered = d.is_registered_to_account and d.registration_status == "REGISTERED"
        ind.append(_Indicator(
            0.0 if registered else 1.0,
            (f"device registry: status={d.registration_status}, "
             f"registered_to_account={d.is_registered_to_account}"),
            _evidence_ref(dev, f"device_id={d.device_id}"),
        ))
    elif dev is not None and dev.status == EvidenceStatus.NOT_FOUND:
        ind.append(_Indicator(
            1.0, "device not found in device registry (unknown device)",
            _evidence_ref(dev),
        ))
    return _combine(RiskSignal.NEW_DEVICE, ind,
                    "No device flag on transaction and no usable device-registry evidence.")


# ---------------------------------------------------------------------------
# NEW_BENEFICIARY
# ---------------------------------------------------------------------------

def extract_new_beneficiary(tx: CanonicalTransaction, agent2: Any,
                            cfg: Agent4Config) -> SignalResult:
    ind: list[_Indicator] = []
    flag = tx.metadata.is_new_beneficiary if tx.metadata else None
    if flag is not None:
        ind.append(_Indicator(
            1.0 if flag else 0.0,
            f"transaction flags is_new_beneficiary={flag}",
            _tx_ref(tx, "metadata.is_new_beneficiary"),
        ))

    ben = getattr(agent2, "beneficiary", None) if agent2 is not None else None
    if _found(ben):
        b = ben.data
        if b.previous_fraud_flag:
            ind.append(_Indicator(1.0, "beneficiary previously flagged for fraud",
                                  _evidence_ref(ben, f"account_id={b.account_id}")))
        elif b.known_transaction_count == 0:
            ind.append(_Indicator(1.0, "beneficiary has no known prior transactions",
                                  _evidence_ref(ben, f"account_id={b.account_id}")))
        elif (b.account_age_days is not None
              and b.account_age_days < cfg.new_beneficiary_account_age_days):
            ind.append(_Indicator(
                0.5,
                (f"beneficiary account age {b.account_age_days}d "
                 f"< {cfg.new_beneficiary_account_age_days}d"),
                _evidence_ref(ben, f"account_id={b.account_id}")))
        else:
            ind.append(_Indicator(0.0, "beneficiary established with prior transactions",
                                  _evidence_ref(ben, f"account_id={b.account_id}")))
    elif ben is not None and ben.status == EvidenceStatus.NOT_FOUND:
        ind.append(_Indicator(1.0, "beneficiary not found in beneficiary records",
                              _evidence_ref(ben)))

    cb = getattr(agent2, "core_banking", None) if agent2 is not None else None
    receiver = tx.receiver.account_id if tx.receiver else None
    if _found(cb) and cb.data.stats is not None and receiver:
        known = receiver in cb.data.stats.known_beneficiaries
        ind.append(_Indicator(
            0.0 if known else 1.0,
            f"receiver {'is' if known else 'is NOT'} in sender's known beneficiaries",
            _evidence_ref(cb, f"account_id={cb.data.account_id}"),
        ))
    return _combine(RiskSignal.NEW_BENEFICIARY, ind,
                    "No beneficiary flag on transaction and no usable beneficiary evidence.")


# ---------------------------------------------------------------------------
# UNUSUAL_TIMING
# ---------------------------------------------------------------------------

def extract_unusual_timing(tx: CanonicalTransaction, cfg: Agent4Config) -> SignalResult:
    ind: list[_Indicator] = []
    if tx.timestamp is not None:
        hour = tx.timestamp.hour  # local hour in the timestamp's own offset
        night = cfg.is_night_hour(hour)
        ind.append(_Indicator(
            1.0 if night else 0.0,
            (f"local hour {hour:02d}:xx is "
             f"{'inside' if night else 'outside'} night window "
             f"{cfg.night_start_hour:02d}:00–{cfg.night_end_hour:02d}:00"),
            _tx_ref(tx, "timestamp"),
        ))
    mins = tx.metadata.time_since_beneficiary_added_min if tx.metadata else None
    if mins is not None:
        recent = mins < cfg.recent_beneficiary_minutes
        ind.append(_Indicator(
            1.0 if recent else 0.0,
            (f"beneficiary added {mins} min before payment "
             f"({'<' if recent else '>='} {cfg.recent_beneficiary_minutes} min)"),
            _tx_ref(tx, "metadata.time_since_beneficiary_added_min"),
        ))
    return _combine(RiskSignal.UNUSUAL_TIMING, ind,
                    "Transaction timestamp and beneficiary-added timing unavailable.")


# ---------------------------------------------------------------------------
# NETWORK_RISK (Agent 3)
# ---------------------------------------------------------------------------

def extract_network_risk(agent3: Any, cfg: Agent4Config) -> SignalResult:
    sig = RiskSignal.NETWORK_RISK
    if agent3 is None:
        return SignalResult(sig, None, "Agent 3 output not available.")
    status = getattr(agent3.status, "value", str(agent3.status))
    if status not in ("COMPLETE", "PARTIAL"):
        return SignalResult(sig, None,
                            f"Agent 3 status {status}; network analysis incomplete — not treated as clean.")

    if not agent3.findings:
        if status == "PARTIAL":
            return SignalResult(sig, None,
                                "Agent 3 PARTIAL with no findings; absence of patterns not confirmed.")
        return SignalResult(
            sig, 0.0, "Agent 3 COMPLETE: no network patterns met configured thresholds.",
            evidence_refs=[EvidenceRef(source_agent="AGENT_3", source="NetworkAnalyser",
                                       reference_id=agent3.agent3_run_id,
                                       retrieved_at=_iso(agent3.analysed_at_utc))],
        )

    ind = []
    for f in agent3.findings:
        score = f.heuristic_score
        note = ""
        if score is None:
            score = cfg.network_finding_default_score
            note = " (no heuristic score; default applied)"
        ind.append(_Indicator(
            float(score),
            f"{enum_str(f.pattern_type)} [{f.rule_id}] heuristic={score:.2f}{note}",
            EvidenceRef(source_agent="AGENT_3", source=f.rule_id,
                        reference_id=f.finding_id,
                        retrieved_at=f.query_timestamp_utc,
                        detail=f"subject_account={f.subject_account_id}"),
        ))
    result = _combine(sig, ind, "")
    if status == "PARTIAL":
        result.warnings.append("Agent 3 PARTIAL: some detectors did not run.")
    return result


# ---------------------------------------------------------------------------
# SANCTIONS_HIT (Agent 2)
# ---------------------------------------------------------------------------

_SCREEN_FAILURES = {EvidenceStatus.PROVIDER_ERROR, EvidenceStatus.AUTH_ERROR}


@dataclass
class SanctionsAssessment:
    result: SignalResult
    match_found: bool
    screening_failed: bool
    """True when an attempted screen failed (provider/auth error) or no screen completed."""


def extract_sanctions(agent2: Any) -> SanctionsAssessment:
    sig = RiskSignal.SANCTIONS_HIT
    if agent2 is None:
        return SanctionsAssessment(
            SignalResult(sig, None, "Agent 2 output not available; sanctions not screened."),
            match_found=False, screening_failed=True)

    provider_status = {pr.provider_name: pr.status for pr in agent2.provider_results}
    ind: list[_Indicator] = []
    failed_screens: list[str] = []
    match = False

    for name, resp in (("SANCTIONS_SUBJECT", agent2.sanctions_subject),
                       ("SANCTIONS_ACCOUNT", agent2.sanctions_account)):
        if resp is not None and (resp.status == EvidenceStatus.MATCH_FOUND
                                 or (resp.data is not None and resp.data.matched)):
            match = True
            d = resp.data
            detail = (f"list={d.list_name}, confidence={d.match_confidence}, "
                      f"method={d.matching_method}") if d else None
            ind.append(_Indicator(1.0, f"{name}: MATCH_FOUND", _evidence_ref(resp, detail)))
        elif resp is not None and resp.status == EvidenceStatus.NO_MATCH:
            ind.append(_Indicator(0.0, f"{name}: NO_MATCH", _evidence_ref(resp)))
        else:
            st = resp.status if resp is not None else provider_status.get(name)
            if st in _SCREEN_FAILURES:
                failed_screens.append(f"{name}: {st.value}")
            elif st == EvidenceStatus.VALIDATION_ERROR:
                pass  # not attempted (missing identifier) — recorded as warning below
            elif st is None:
                failed_screens.append(f"{name}: no result")

    result = _combine(sig, ind, "No sanctions screen completed; sanctions status unknown.")
    not_attempted = [n for n in ("SANCTIONS_SUBJECT", "SANCTIONS_ACCOUNT")
                     if provider_status.get(n) == EvidenceStatus.VALIDATION_ERROR]
    for n in not_attempted:
        result.warnings.append(f"{n} not attempted (missing identifier).")
    for f in failed_screens:
        result.warnings.append(f"Sanctions screen failed — {f}. Not treated as clean.")

    screening_failed = bool(failed_screens) or not result.available
    return SanctionsAssessment(result, match_found=match,
                               screening_failed=screening_failed and not match)


# ---------------------------------------------------------------------------
# LOCATION_ANOMALY (Agent 2 geolocation)
# ---------------------------------------------------------------------------

def extract_location(agent2: Any) -> SignalResult:
    sig = RiskSignal.LOCATION_ANOMALY
    geo = getattr(agent2, "geolocation", None) if agent2 is not None else None
    if not _found(geo):
        return SignalResult(sig, None, "No usable geolocation evidence.")
    d = geo.data
    if d.is_anomalous is None:
        return SignalResult(sig, None, "Geolocation coordinates unavailable; anomaly undetermined.",
                            evidence_refs=[_evidence_ref(geo)])
    dist = f"{d.distance_km:.0f} km" if d.distance_km is not None else "unknown distance"
    reason = (f"transaction {dist} from registered location; "
              f"is_anomalous={d.is_anomalous}")
    if d.anomaly_reason:
        reason += f" ({d.anomaly_reason})"
    return SignalResult(sig, 1.0 if d.is_anomalous else 0.0, reason,
                        evidence_refs=[_evidence_ref(geo, f"account_id={d.account_id}")])
