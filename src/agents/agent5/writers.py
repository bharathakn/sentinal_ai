"""
Sentinel AI — Agent 5: deterministic writers.

* ``system_sections``: content that is never written by the LLM —
  the decision block of Recommended Action, the Regulatory Assessment and the
  Source Audit Trail. Built only from Agent 4 / audit facts.
* ``template_narrative``: the fallback writer for the narrative sections
  (Case Summary, Anomaly Findings, Evidence Summary, Network Analysis and the
  narrative part of Recommended Action). Every statement quotes fact values
  verbatim and cites the facts it uses.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Optional

from .facts import fmt_dt
from .report_schema import (
    NOT_IDENTIFIED,
    EvidenceBundle,
    Fact,
    ReportSection,
    Statement,
    StatementOrigin,
)

TEMPLATE_VERSION = "1.0.0"
S = ReportSection


class _Index:
    def __init__(self, bundle: EvidenceBundle) -> None:
        self.bundle = bundle
        self.by_section: dict[ReportSection, list[Fact]] = {s: [] for s in ReportSection}
        for f in bundle.facts:
            self.by_section[f.section].append(f)

    def first(self, section: ReportSection, label: str) -> Optional[Fact]:
        for f in self.by_section[section]:
            if f.label == label:
                return f
        return None

    def startswith(self, section: ReportSection, prefix: str) -> list[Fact]:
        return [f for f in self.by_section[section] if f.label.startswith(prefix)]


def _stmt(text: str, facts: list[Optional[Fact]], origin: StatementOrigin) -> Optional[Statement]:
    ids = [f.fact_id for f in facts if f is not None]
    if not ids:
        return None
    return Statement(text=text, fact_ids=ids, origin=origin)


def _v(f: Optional[Fact]) -> str:
    return f.value if f is not None else NOT_IDENTIFIED


def _line(f: Fact, origin: StatementOrigin) -> Statement:
    end = "" if f.value.rstrip().endswith((".", "!", "?")) else "."
    return Statement(text=f"{f.label}: {f.value}{end}", fact_ids=[f.fact_id], origin=origin)


# ---------------------------------------------------------------------------
# System (never LLM) sections
# ---------------------------------------------------------------------------

def system_decision(bundle: EvidenceBundle) -> list[Statement]:
    ix = _Index(bundle)
    R, O = S.RECOMMENDED_ACTION, StatementOrigin.SYSTEM
    action, score = ix.first(R, "Recommended action"), ix.first(R, "Risk score")
    band, conf = ix.first(R, "Score band action"), ix.first(R, "Assessment confidence")
    sar, note = ix.first(R, "SAR/STR recommendation"), ix.first(R, "SAR/STR note")
    cfg = ix.first(R, "Risk configuration")
    out = [
        _stmt(f"Recommended action: {_v(action)}. Risk score: {_v(score)} (score band action "
              f"{_v(band)}). Confidence: {_v(conf)}.", [action, score, band, conf], O),
        _stmt(f"SAR/STR recommendation: {_v(sar)}. {_v(note)}", [sar, note], O),
        _stmt(f"Risk configuration: {_v(cfg)}.", [cfg], O),
    ]
    out += [_line(f, O) for f in ix.startswith(R, "Override ")]
    if not ix.startswith(R, "Override "):
        f = ix.first(R, "Overrides applied")
        if f:
            out.append(_line(f, O))
    if action is None:  # Agent 4 absent
        f = ix.first(R, "Risk assessment")
        if f:
            out.append(_stmt(f"Risk assessment: {f.value}. The case requires human review.", [f], O))
    return [s for s in out if s is not None]


def system_regulatory(bundle: EvidenceBundle) -> list[Statement]:
    O = StatementOrigin.SYSTEM
    return [_line(f, O) for f in _Index(bundle).by_section[S.REGULATORY_ASSESSMENT]]


def system_audit(bundle: EvidenceBundle) -> list[Statement]:
    """Group every fact by its source so each source is listed once with the facts it supplied."""
    O = StatementOrigin.SYSTEM
    groups: "OrderedDict[tuple, list[Fact]]" = OrderedDict()
    for f in bundle.facts:
        key = (f.source_agent.value, f.source, f.source_mode, f.reference_id, f.observed_at)
        groups.setdefault(key, []).append(f)
    out = []
    for (agent, source, mode, ref, observed), facts in groups.items():
        parts = [f"{agent} / {source}"]
        if mode:
            parts.append(f"mode {mode}")
        if observed:
            parts.append(f"at {fmt_dt(observed)}")
        if ref:
            parts.append(f"ref {ref}")
        ids = [f.fact_id for f in facts]
        span = ids[0] if len(ids) == 1 else f"{ids[0]}…{ids[-1]} ({len(ids)} facts)"
        out.append(Statement(text=f"{'; '.join(parts)}: {span}.", fact_ids=ids, origin=O))
    return out


# ---------------------------------------------------------------------------
# Template narrative (fallback for LLM sections)
# ---------------------------------------------------------------------------

def template_narrative(bundle: EvidenceBundle) -> dict[ReportSection, list[Statement]]:
    ix = _Index(bundle)
    T = StatementOrigin.TEMPLATE
    out: dict[ReportSection, list[Statement]] = {}

    # 1. Case summary
    C = S.CASE_SUMMARY
    g = lambda label: ix.first(C, label)  # noqa: E731
    used: set[str] = set()

    def track(*facts: Optional[Fact]) -> list[Optional[Fact]]:
        used.update(f.fact_id for f in facts if f is not None)
        return list(facts)

    cs = [
        _stmt(f"Case {_v(g('Case id'))} was opened at {_v(g('Case opened at'))} for transaction "
              f"{_v(g('Transaction id'))} from the {_v(g('Source dataset'))} dataset.",
              track(g("Case id"), g("Case opened at"), g("Transaction id"), g("Source dataset")), T),
        _stmt(f"The transaction moved {_v(g('Amount'))} via {_v(g('Channel'))} (type "
              f"{_v(g('Transaction type'))}) from account {_v(g('Sender account'))} to account "
              f"{_v(g('Receiver account'))} at {_v(g('Transaction time'))}; status {_v(g('Transaction status'))}.",
              track(g("Amount"), g("Channel"), g("Transaction type"), g("Sender account"),
                    g("Receiver account"), g("Transaction time"), g("Transaction status")), T),
        _stmt(f"Sender: {_v(g('Sender customer name'))} (customer {_v(g('Sender customer id'))}). "
              f"Receiver: {_v(g('Receiver customer name'))} (customer {_v(g('Receiver customer id'))}).",
              track(g("Sender customer name"), g("Sender customer id"),
                    g("Receiver customer name"), g("Receiver customer id")), T),
        _stmt(f"Device {_v(g('Device id'))}; transaction location {_v(g('Transaction location'))}.",
              track(g("Device id"), g("Transaction location")), T),
    ]
    cs += [_line(f, T) for f in ix.by_section[C] if f.fact_id not in used]
    out[C] = [s for s in cs if s is not None]

    # 2. Anomaly findings
    A = S.ANOMALY_FINDINGS
    mode, x = ix.first(A, "Scoring mode"), ix.first(A, "XGBoost fraud score")
    i, c = ix.first(A, "Isolation Forest anomaly score"), ix.first(A, "Combined model signal")
    lead = _stmt(f"Agent 1 (scoring mode {_v(mode)}) produced an XGBoost fraud score of {_v(x)}, an "
                 f"Isolation Forest anomaly score of {_v(i)} and a combined model signal of {_v(c)}.",
                 [mode, x, i, c], T)
    lead_ids = set(lead.fact_ids) if lead else set()
    out[A] = ([lead] if lead else []) + [_line(f, T) for f in ix.by_section[A] if f.fact_id not in lead_ids]

    # 3–4. Evidence and network: one statement per fact
    for sec in (S.EVIDENCE_SUMMARY, S.NETWORK_ANALYSIS):
        out[sec] = [_line(f, T) for f in ix.by_section[sec]]

    # 6. Recommended action narrative: what drove the score
    R = S.RECOMMENDED_ACTION
    sig = [f for f in ix.startswith(R, "Signal ") if not f.label.startswith("Signals unavailable")]
    narrative = [_line(f, T) for f in sig]
    for label in ("Evidence coverage", "Signals unavailable (not scored as safe)"):
        f = ix.first(R, label)
        if f:
            narrative.append(_line(f, T))
    out[R] = narrative
    return out
