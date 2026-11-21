"""
Sentinel AI — Agent 5: deterministic evidence-bundle builder.

Turns a case state (transaction + Agent 1–4 outputs) into a flat, ordered list
of :class:`Fact` objects. This is the ONLY information the report writer (LLM
or template) receives, and the reference the Output Validator checks against.

Rules
-----
* Values are formatted here, once, so the report can quote them exactly.
* Missing values are rendered as ``Not identified`` (never omitted silently
  for key fields, never guessed).
* Ground-truth fields are never read: the transaction is passed through
  ``strip_ground_truth`` again (defence in depth) and label-like account types
  are excluded.
* Fact ids are assigned in a fixed traversal order (F-001, F-002, …).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional

from .report_schema import NOT_IDENTIFIED, EvidenceBundle, Fact, ReportSection, SourceAgent

BUILDER_VERSION = "1.0.0"
MAX_SHAP_FEATURES = 5
MAX_TRANSFERS_PER_FINDING = 6
MAX_NEWS_ARTICLES = 3
MAX_WARNINGS_PER_SOURCE = 3

_LABEL_ACCOUNT_TYPES = {"MULE_SUSPECT"}

S = ReportSection


# ---------------------------------------------------------------------------
# Formatting (deterministic)
# ---------------------------------------------------------------------------

def _enum(v: Any) -> Optional[str]:
    if v is None:
        return None
    return getattr(v, "value", str(v))


def fmt_amount(amount: Any, currency: Optional[str] = "INR") -> str:
    if amount is None:
        return NOT_IDENTIFIED
    try:
        d = Decimal(str(amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return NOT_IDENTIFIED
    return f"{currency or ''} {d:,.2f}".strip()


def fmt_dt(dt: Any) -> str:
    """UTC, second precision: '2026-08-03 14:42:29 UTC'."""
    if dt is None or dt == "":
        return NOT_IDENTIFIED
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def fmt_local_and_utc(dt: Optional[datetime]) -> str:
    if dt is None:
        return NOT_IDENTIFIED
    if dt.tzinfo is None or dt.utcoffset() == timezone.utc.utcoffset(None):
        return fmt_dt(dt)
    return f"{dt.strftime('%Y-%m-%d %H:%M:%S %z')} local ({fmt_dt(dt)})"


def fmt_num(v: Any, places: int = 3) -> str:
    if v is None:
        return NOT_IDENTIFIED
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, int):
        return f"{v:,}"
    try:
        return f"{float(v):.{places}f}"
    except (TypeError, ValueError):
        return str(v)


def fmt_bool(v: Optional[bool]) -> str:
    return NOT_IDENTIFIED if v is None else ("Yes" if v else "No")


def fmt_str(v: Any) -> str:
    if v is None:
        return NOT_IDENTIFIED
    s = str(_enum(v)).strip()
    return s if s else NOT_IDENTIFIED


def fmt_list(items: Iterable[Any]) -> str:
    vals = [str(_enum(i)) for i in items if i is not None and str(i) != ""]
    return ", ".join(vals) if vals else "None"


def _iso(dt: Any) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    return str(dt)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class _Facts:
    def __init__(self) -> None:
        self.items: list[Fact] = []

    def add(self, section: ReportSection, label: str, value: str, source_agent: SourceAgent,
            source: str, source_field: str, *, source_mode: Optional[str] = None,
            observed_at: Any = None, reference_id: Optional[str] = None) -> str:
        fid = f"F-{len(self.items) + 1:03d}"
        self.items.append(Fact(
            fact_id=fid, section=section, label=label, value=value,
            source_agent=source_agent, source=source, source_field=source_field,
            source_mode=source_mode, observed_at=_iso(observed_at), reference_id=reference_id,
        ))
        return fid


def build_evidence_bundle(state: dict) -> EvidenceBundle:
    """Build the evidence bundle for a case state. Never raises for missing outputs."""
    from ..sentinel_pipeline import strip_ground_truth  # local: sentinel_pipeline imports agent5 schemas
    fb = _Facts()
    missing: list[str] = []

    tx = state.get("transaction")
    if tx is not None:
        tx = strip_ground_truth(tx)
    a1 = state.get("agent1_output")
    a2 = state.get("agent2_output")
    a3 = state.get("agent3_output")
    a4 = state.get("agent4_output")
    for name, obj in (("transaction", tx), ("agent1_output", a1), ("agent2_output", a2),
                      ("agent3_output", a3), ("agent4_output", a4)):
        if obj is None:
            missing.append(name)

    _case_facts(fb, state, tx, a2)
    _anomaly_facts(fb, a1, tx)
    _evidence_facts(fb, a2)
    _network_facts(fb, a3)
    _decision_facts(fb, a4)

    payload = json.dumps([f.model_dump(mode="json") for f in fb.items], sort_keys=True, ensure_ascii=False)
    return EvidenceBundle(
        case_id=state.get("case_id"),
        transaction_id=getattr(tx, "raw_record_id", None),
        built_at_utc=datetime.now(timezone.utc),
        facts=fb.items,
        bundle_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        builder_version=BUILDER_VERSION,
        missing_inputs=missing,
    )


# ---------------------------------------------------------------------------
# 1. Case summary
# ---------------------------------------------------------------------------

def _case_facts(fb: _Facts, state: dict, tx: Any, a2: Any) -> None:
    C, T = SourceAgent.CASE, SourceAgent.TRANSACTION
    fb.add(S.CASE_SUMMARY, "Case id", fmt_str(state.get("case_id")), C, "CASE", "case_id")
    fb.add(S.CASE_SUMMARY, "Case opened at", fmt_dt(state.get("case_created_at_utc")), C, "CASE",
           "case_created_at_utc")
    if tx is None:
        fb.add(S.CASE_SUMMARY, "Transaction", NOT_IDENTIFIED, T, "TRANSACTION", "transaction")
        return
    src = f"{_enum(tx.source_dataset)}_DATASET"
    mode = "SYNTHETIC" if "SYNTHETIC" in str(_enum(tx.source_dataset)) else None
    add = lambda label, value, field: fb.add(S.CASE_SUMMARY, label, value, T, src,  # noqa: E731
                                             f"transaction.{field}", source_mode=mode)
    add("Transaction id", fmt_str(tx.raw_record_id), "raw_record_id")
    add("Source dataset", fmt_str(tx.source_dataset), "source_dataset")
    add("Amount", fmt_amount(tx.amount, tx.currency), "amount")
    add("Transaction time", fmt_local_and_utc(tx.timestamp), "timestamp")
    add("Channel", fmt_str(tx.channel), "channel")
    add("Transaction status", fmt_str(tx.status), "status")
    add("Transaction type", fmt_str(getattr(tx.metadata, "transaction_type", None)), "metadata.transaction_type")
    add("Sender account", fmt_str(tx.sender.account_id), "sender.account_id")
    add("Sender customer id", fmt_str(tx.sender.customer_id), "sender.customer_id")
    add("Receiver account", fmt_str(tx.receiver.account_id), "receiver.account_id")
    add("Receiver customer id", fmt_str(tx.receiver.customer_id), "receiver.customer_id")
    add("Device id", fmt_str(tx.device.device_id), "device.device_id")
    add("Transaction location", fmt_str(", ".join(x for x in (tx.location.city, tx.location.state,
                                                                tx.location.country) if x) or None),
        "location")

    kyc = getattr(a2, "kyc", None) if a2 is not None else None
    kd = getattr(kyc, "data", None)
    fb.add(S.CASE_SUMMARY, "Sender customer name", fmt_str(getattr(kd, "customer_name", None)),
           SourceAgent.AGENT_2, getattr(kyc, "source", "KYC"), "agent2_output.kyc.data.customer_name",
           source_mode=_enum(getattr(kyc, "source_mode", None)),
           observed_at=getattr(kyc, "retrieved_at", None), reference_id=getattr(kyc, "request_id", None))
    ben = getattr(a2, "beneficiary", None) if a2 is not None else None
    bd = getattr(ben, "data", None)
    fb.add(S.CASE_SUMMARY, "Receiver customer name", fmt_str(getattr(bd, "customer_name", None)),
           SourceAgent.AGENT_2, getattr(ben, "source", "BENEFICIARY"),
           "agent2_output.beneficiary.data.customer_name",
           source_mode=_enum(getattr(ben, "source_mode", None)),
           observed_at=getattr(ben, "retrieved_at", None), reference_id=getattr(ben, "request_id", None))
    if mode == "SYNTHETIC":
        add("Data notice", "All case data is SYNTHETIC; no real customer or account is involved.",
            "source_dataset")


# ---------------------------------------------------------------------------
# 2. Anomaly findings (Agent 1 + transaction behaviour)
# ---------------------------------------------------------------------------

def _anomaly_facts(fb: _Facts, a1: Any, tx: Any) -> None:
    A = SourceAgent.AGENT_1
    if a1 is None:
        fb.add(S.ANOMALY_FINDINGS, "Agent 1 anomaly detection", NOT_IDENTIFIED, A, "AGENT_1", "agent1_output")
    else:
        ts, ref = a1.scored_at_utc, a1.transaction_id
        fm = a1.feature_mapping
        add = lambda label, value, field, source="AGENT_1": fb.add(  # noqa: E731
            S.ANOMALY_FINDINGS, label, value, A, source, f"agent1_output.{field}", observed_at=ts, reference_id=ref)
        add("Agent 1 status", fmt_str(a1.status), "status")
        add("Scoring mode", fmt_str(getattr(fm, "scoring_mode", None)), "feature_mapping.scoring_mode")
        x = a1.xgboost_detail
        if x is not None:
            src = f"XGBOOST:{x.model_version or 'unknown'}"
            add("XGBoost fraud score", f"{x.fraud_probability:.3f} (threshold {x.threshold_used:.3f}; "
                f"{'above' if x.is_fraud_predicted else 'below'} threshold)", "xgboost_detail", src)
        else:
            add("XGBoost fraud score", NOT_IDENTIFIED, "xgboost_detail")
        i = a1.isolation_forest_detail
        if i is not None:
            src = f"ISOLATION_FOREST:{i.model_version or 'unknown'}"
            add("Isolation Forest anomaly score", f"{i.anomaly_score:.3f} (threshold {i.threshold_used:.3f}; "
                f"{'anomalous' if i.is_anomaly else 'not anomalous'})", "isolation_forest_detail", src)
        else:
            add("Isolation Forest anomaly score", NOT_IDENTIFIED, "isolation_forest_detail")
        add("Combined model signal",
            NOT_IDENTIFIED if a1.combined_confidence is None
            else f"{a1.combined_confidence:.3f} (heuristic composite, not a probability)",
            "combined_confidence")
        for f in a1.top_deviation_features[:MAX_SHAP_FEATURES]:
            direction = "raises" if "increase" in f.direction else "lowers"
            add(f"Model driver #{f.rank}",
                f"{f.feature} = {fmt_num(f.feature_value)} ({direction} the model score; SHAP {f.shap_value:+.3f})",
                f"top_deviation_features[{f.rank - 1}]")
        for w in a1.warnings[:MAX_WARNINGS_PER_SOURCE]:
            add("Agent 1 warning", w, "warnings")
    if tx is not None and tx.metadata is not None:
        m = tx.metadata
        T = SourceAgent.TRANSACTION
        src = f"{_enum(tx.source_dataset)}_DATASET"
        for label, value, field in (
            ("Amount vs sender's 30-day average", "Not identified" if m.amount_ratio_vs_30d_avg is None
             else f"{m.amount_ratio_vs_30d_avg:.2f}x", "amount_ratio_vs_30d_avg"),
            ("Sender transactions in previous 24h", fmt_num(m.tx_frequency_24h), "tx_frequency_24h"),
            ("Time since sender's previous transaction", NOT_IDENTIFIED if m.time_since_last_tx_sec is None
             else f"{m.time_since_last_tx_sec:,} seconds", "time_since_last_tx_sec"),
        ):
            fb.add(S.ANOMALY_FINDINGS, label, value, T, src, f"transaction.metadata.{field}")


# ---------------------------------------------------------------------------
# 3. Evidence summary (Agent 2)
# ---------------------------------------------------------------------------

def _ev(fb: _Facts, resp: Any, field: str, label: str, value: str) -> str:
    return fb.add(S.EVIDENCE_SUMMARY, label, value, SourceAgent.AGENT_2,
                  getattr(resp, "source", field.upper()), f"agent2_output.{field}",
                  source_mode=_enum(getattr(resp, "source_mode", None)),
                  observed_at=getattr(resp, "retrieved_at", None),
                  reference_id=getattr(resp, "request_id", None))


def _evidence_facts(fb: _Facts, a2: Any) -> None:
    if a2 is None:
        fb.add(S.EVIDENCE_SUMMARY, "Agent 2 evidence gathering", NOT_IDENTIFIED, SourceAgent.AGENT_2,
               "AGENT_2", "agent2_output")
        return
    fb.add(S.EVIDENCE_SUMMARY, "Agent 2 status", fmt_str(a2.status), SourceAgent.AGENT_2, "AGENT_2",
           "agent2_output.status", observed_at=a2.gathered_at_utc, reference_id=a2.agent2_run_id)
    if a2.failed_providers:
        fb.add(S.EVIDENCE_SUMMARY, "Evidence sources that failed", fmt_list(a2.failed_providers),
               SourceAgent.AGENT_2, "AGENT_2", "agent2_output.failed_providers",
               observed_at=a2.gathered_at_utc, reference_id=a2.agent2_run_id)

    def unavailable(resp: Any, field: str, label: str) -> bool:
        if resp is None:
            _ev(fb, None, field, label, NOT_IDENTIFIED)
            return True
        if resp.data is None:
            _ev(fb, resp, field, label, f"No data (status {_enum(resp.status)})")
            return True
        return False

    def warnings(resp: Any, field: str, label: str) -> None:
        for w in (resp.warnings if resp is not None else [])[:MAX_WARNINGS_PER_SOURCE]:
            _ev(fb, resp, f"{field}.warnings", label, w)

    # Core banking
    cb = a2.core_banking
    if not unavailable(cb, "core_banking", "Sender account history"):
        st = cb.data.stats
        _ev(fb, cb, "core_banking.data.transaction_history", "Prior transactions retrieved for sender",
            f"{len(cb.data.transaction_history):,}")
        if st is not None:
            _ev(fb, cb, "core_banking.data.stats.num_transactions_30d", "Sender transactions in prior 30 days (credits and debits)",
                fmt_num(st.num_transactions_30d))
            none = f"{NOT_IDENTIFIED} (no prior transactions in the window)"
            no_hist = not st.num_transactions_30d
            _ev(fb, cb, "core_banking.data.stats.avg_debit_amount_inr", "Sender average debit amount (prior 30 days; debits only)",
                none if no_hist else fmt_amount(st.avg_debit_amount_inr))
            _ev(fb, cb, "core_banking.data.stats.max_debit_30d_inr", "Sender largest single debit (prior 30 days)",
                none if no_hist else fmt_amount(st.max_debit_30d_inr))
            _ev(fb, cb, "core_banking.data.stats.known_beneficiaries", "Sender known beneficiaries (count)",
                f"{len(st.known_beneficiaries):,}")
        warnings(cb, "core_banking", "Core banking note")

    # KYC
    k = a2.kyc
    if not unavailable(k, "kyc", "Sender KYC record"):
        d = k.data
        _ev(fb, k, "kyc.data.kyc_status", "Sender KYC status", fmt_str(d.kyc_status))
        _ev(fb, k, "kyc.data.pep", "Sender politically exposed person (PEP)", fmt_bool(d.pep))
        if d.account_type not in _LABEL_ACCOUNT_TYPES:
            _ev(fb, k, "kyc.data.account_type", "Sender account type", fmt_str(d.account_type))
        _ev(fb, k, "kyc.data.account_opening_date", "Sender account opened", fmt_dt(d.account_opening_date))
        _ev(fb, k, "kyc.data.income_band", "Sender declared income band", fmt_str(d.income_band))
        _ev(fb, k, "kyc.data.registered_city", "Sender registered location",
            fmt_str(", ".join(x for x in (d.registered_city, d.registered_state, d.registered_country) if x) or None))
        warnings(k, "kyc", "KYC note")

    # Device
    dv = a2.device
    if not unavailable(dv, "device", "Device registry record"):
        d = dv.data
        _ev(fb, dv, "device.data.registration_status", "Device registration status", fmt_str(d.registration_status))
        _ev(fb, dv, "device.data.is_registered_to_account", "Device registered to sender account",
            fmt_bool(d.is_registered_to_account))
        _ev(fb, dv, "device.data.num_associated_accounts", "Accounts that have used this device",
            fmt_num(d.num_associated_accounts))
        _ev(fb, dv, "device.data.first_seen", "Device first seen", fmt_dt(d.first_seen))
        _ev(fb, dv, "device.data.device_type", "Device type", fmt_str(d.device_type))
        warnings(dv, "device", "Device registry note")

    # Beneficiary
    b = a2.beneficiary
    if not unavailable(b, "beneficiary", "Receiver (beneficiary) record"):
        d = b.data
        _ev(fb, b, "beneficiary.data.account_age_days", "Receiver account age",
            NOT_IDENTIFIED if d.account_age_days is None else f"{d.account_age_days:,} days")
        _ev(fb, b, "beneficiary.data.kyc_status", "Receiver KYC status", fmt_str(d.kyc_status))
        _ev(fb, b, "beneficiary.data.previous_fraud_flag", "Receiver previous fraud flag",
            fmt_bool(d.previous_fraud_flag))
        warnings(b, "beneficiary", "Beneficiary note")

    # Sanctions
    for field, label in (("sanctions_subject", "Sanctions screening (sender name)"),
                         ("sanctions_account", "Sanctions screening (sender account)")):
        r = getattr(a2, field)
        if r is None:
            _ev(fb, None, field, label, NOT_IDENTIFIED)
            continue
        d = r.data
        if d is None:
            _ev(fb, r, f"{field}.status", label, f"Not completed (status {_enum(r.status)})")
        else:
            res = "MATCH" if d.matched else "No match"
            extra = f"; list {d.list_name}" if d.list_name else ""
            _ev(fb, r, f"{field}.data.matched", label,
                f"{res} (status {_enum(r.status)}; method {d.matching_method or NOT_IDENTIFIED}{extra})")
            _ev(fb, r, f"{field}.data.screening_disclaimer", f"{label}: disclaimer", d.screening_disclaimer)
        warnings(r, field, "Sanctions note")

    # Geolocation
    g = a2.geolocation
    if not unavailable(g, "geolocation", "Location check"):
        d = g.data
        _ev(fb, g, "geolocation.data.transaction_city", "Transaction city", fmt_str(d.transaction_city))
        _ev(fb, g, "geolocation.data.registered_city", "Sender registered city", fmt_str(d.registered_city))
        _ev(fb, g, "geolocation.data.distance_km", "Distance from registered location",
            NOT_IDENTIFIED if d.distance_km is None else f"{d.distance_km:,.2f} km")
        _ev(fb, g, "geolocation.data.is_anomalous", "Location flagged unusual", fmt_bool(d.is_anomalous))
        if d.anomaly_reason:
            _ev(fb, g, "geolocation.data.anomaly_reason", "Location note", d.anomaly_reason)

    # News
    n = a2.news
    if not unavailable(n, "news", "Adverse media search"):
        d = n.data
        _ev(fb, n, "news.data.total_results", "Adverse media search result",
            f"{d.total_results:,} article(s) (status {_enum(n.status)})")
        for i, art in enumerate(d.articles[:MAX_NEWS_ARTICLES]):
            _ev(fb, n, f"news.data.articles[{i}]", "News article (unverified; may concern a different entity)",
                f"\"{art.title}\" — {art.source}, {art.published_at or NOT_IDENTIFIED}")
        warnings(n, "news", "Adverse media note")

    # Provider audit
    for pr in a2.provider_results:
        fb.add(S.SOURCE_AUDIT_TRAIL, "Evidence source", f"{pr.provider_name}: {_enum(pr.status)}"
               + (f" ({pr.error_summary})" if pr.error_summary else "") + (" [timed out]" if pr.timed_out else ""),
               SourceAgent.AGENT_2, pr.provider_name, "agent2_output.provider_results",
               observed_at=pr.retrieved_at, reference_id=a2.agent2_run_id)


# ---------------------------------------------------------------------------
# 4. Network analysis (Agent 3)
# ---------------------------------------------------------------------------

def _network_facts(fb: _Facts, a3: Any) -> None:
    A = SourceAgent.AGENT_3
    if a3 is None:
        fb.add(S.NETWORK_ANALYSIS, "Agent 3 network analysis", NOT_IDENTIFIED, A, "AGENT_3", "agent3_output")
        return
    ts, run = a3.analysed_at_utc, a3.agent3_run_id
    add = lambda label, value, field, ref=run, src="AGENT_3_GRAPH": fb.add(  # noqa: E731
        S.NETWORK_ANALYSIS, label, value, A, src, f"agent3_output.{field}", observed_at=ts, reference_id=ref)
    status = _enum(a3.status)
    add("Agent 3 status", fmt_str(status), "status")
    add("Accounts present in transaction graph",
        f"sender {fmt_bool(a3.sender_in_graph)}, receiver {fmt_bool(a3.receiver_in_graph)}",
        "sender_in_graph")
    if not a3.findings:
        add("Network patterns detected",
            "None detected" if status == "COMPLETE"
            else f"None reported (analysis status {status}; this is not a clean result)", "findings")
    else:
        add("Network patterns detected", f"{len(a3.findings)} finding(s): "
            + fmt_list(f.pattern_type for f in a3.findings), "findings")
    for idx, f in enumerate(a3.findings):
        p = f"findings[{idx}]"
        label = f"{_enum(f.pattern_type)} finding on {f.subject_account_id}"
        add(label, f.explanation, f"{p}.explanation", f.finding_id, f.rule_id)
        details = [f"rule {f.rule_id}"]
        if f.transfer_count is not None:
            details.append(f"{f.transfer_count} transfers")
        if f.total_amount is not None:
            details.append(f"total {fmt_amount(f.total_amount, f.currency)}")
        if f.elapsed_minutes is not None:
            details.append(f"over {f.elapsed_minutes:,.1f} minutes")
        if f.heuristic_score is not None:
            details.append(f"heuristic score {f.heuristic_score:.3f}")
        add(f"{label}: details", "; ".join(details), p, f.finding_id, f.rule_id)
        add(f"{label}: related accounts", fmt_list(f.related_account_ids), f"{p}.related_account_ids",
            f.finding_id, f.rule_id)
        for j, t in enumerate(f.supporting_transfers[:MAX_TRANSFERS_PER_FINDING]):
            tid = t.raw_record_id or (t.tx_graph_id.split("::")[0] if t.tx_graph_id else None)
            add(f"{label}: transfer {j + 1}",
                f"{fmt_str(tid)}: {fmt_str(t.from_account_id)} → {fmt_str(t.to_account_id)}, "
                f"{fmt_amount(t.amount if t.amount is not None else t.amount_str, t.currency)}, "
                f"{fmt_dt(t.timestamp_utc)}, {fmt_str(t.channel)}",
                f"{p}.supporting_transfers[{j}]", f.finding_id, f.rule_id)
        if len(f.supporting_transfers) > MAX_TRANSFERS_PER_FINDING:
            add(f"{label}: further transfers",
                f"{len(f.supporting_transfers) - MAX_TRANSFERS_PER_FINDING} more not listed",
                f"{p}.supporting_transfers", f.finding_id, f.rule_id)
    for w in a3.warnings[:MAX_WARNINGS_PER_SOURCE]:
        add("Agent 3 warning", w, "warnings")


# ---------------------------------------------------------------------------
# 5–6. Regulatory assessment and decision (Agent 4)
# ---------------------------------------------------------------------------

def _decision_facts(fb: _Facts, a4: Any) -> None:
    A = SourceAgent.AGENT_4
    if a4 is None:
        fb.add(S.RECOMMENDED_ACTION, "Risk assessment", NOT_IDENTIFIED, A, "AGENT_4", "agent4_output")
        fb.add(S.REGULATORY_ASSESSMENT, "Regulatory matches", NOT_IDENTIFIED, A, "AGENT_4",
               "agent4_output.regulatory_matches")
        return
    ts, run = a4.assessed_at_utc, a4.agent4_run_id
    src = f"AGENT_4_RISK_ASSESSOR:config {a4.config_version}"

    def add(section: ReportSection, label: str, value: str, field: str, s: str = src) -> str:
        return fb.add(section, label, value, A, s, f"agent4_output.{field}", observed_at=ts, reference_id=run)

    R = S.RECOMMENDED_ACTION
    add(R, "Agent 4 status", fmt_str(a4.status), "status")
    add(R, "Recommended action", fmt_str(a4.recommended_action), "recommended_action")
    add(R, "Risk score", NOT_IDENTIFIED if a4.risk_score is None else f"{a4.risk_score:.2f} / 100", "risk_score")
    add(R, "Score band action", fmt_str(a4.score_band_action), "score_band_action")
    add(R, "Assessment confidence", f"{_enum(a4.confidence)} ({'; '.join(a4.confidence_reasons) or 'no reasons'})",
        "confidence")
    add(R, "Evidence coverage", f"{a4.evidence_coverage:.2f}", "evidence_coverage")
    add(R, "Signals unavailable (not scored as safe)", fmt_list(a4.unavailable_signals), "unavailable_signals")
    for i, b in enumerate(a4.score_breakdown):
        val = "unavailable" if not b.available else f"value {b.value:.2f}"
        add(R, f"Signal {_enum(b.signal)}",
            f"{val}, weight {b.weight:.2f}, contribution {b.contribution:.3f}: {b.rationale}",
            f"score_breakdown[{i}]")
    if a4.overrides_applied:
        for i, o in enumerate(a4.overrides_applied):
            add(R, f"Override {o.rule_id}", f"minimum action {_enum(o.minimum_action)}: {o.description}",
                f"overrides_applied[{i}]")
    else:
        add(R, "Overrides applied", "None", "overrides_applied")
    sar = a4.sar_recommendation
    add(R, "SAR/STR recommendation",
        ("Recommended" if sar.recommended else "Not recommended")
        + (f" (basis: {fmt_list(sar.basis)})" if sar.basis else ""), "sar_recommendation")
    add(R, "SAR/STR note", sar.note, "sar_recommendation.note")
    add(R, "Risk configuration", f"version {a4.config_version}; {a4.config_approval_status}", "config_version")

    G = S.REGULATORY_ASSESSMENT
    if not a4.regulatory_matches:
        add(G, "Regulatory matches", "None", "regulatory_matches")
    for i, m in enumerate(a4.regulatory_matches):
        add(G, f"Regulatory reference {m.reference_id}",
            f"{m.reference_id} ({m.organization}, {m.section}, PDF page {m.pdf_page}) for trigger "
            f"{_enum(m.trigger)}; status {_enum(m.verification_status)}. Rationale: {m.mapping_rationale}",
            f"regulatory_matches[{i}]", f"REGULATORY_MAPPING:{a4.mapping_version}")
    add(G, "Triggers without an approved regulatory mapping", fmt_list(a4.unmapped_triggers),
        "unmapped_triggers", f"REGULATORY_MAPPING:{a4.mapping_version}")

    for agent, run_id, status in (("Agent 2 run", a4.agent2_run_id, a4.agent2_status),
                                  ("Agent 3 run", a4.agent3_run_id, a4.agent3_status),
                                  ("Agent 4 run", run, a4.status)):
        add(S.SOURCE_AUDIT_TRAIL, agent, f"{fmt_str(run_id)} ({fmt_str(status)})", "agent_runs")
