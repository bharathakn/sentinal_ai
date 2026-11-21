"""
Sentinel AI — grounding tokens shared by Agent 5 and the Output Validator.

A statement is grounded when every concrete token in it — identifiers,
dates, times and numbers — appears in the facts it cites. Both the writer
(citation completion) and the validator use these same functions, so they
agree on what a token is.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .facts import fmt_dt
from .report_schema import EvidenceBundle, Fact, ReportSection, Statement

FACT_REF = re.compile(r"\bF-\d{3}\b")
_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
# Letter-led tokens joined by _ . - that contain a digit: ACC_IND_000917, CASE-1F3B8AD954A1,
# AGENT3.LAYERING.v2, FATF-R10-D, INR_5L_10L, india_behaviour_v1.
_IDENT = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:[_.\-][A-Za-z0-9]+)+\b|\b[A-Za-z]+\d[A-Za-z0-9]*\b")
# (second alternative: letter-led codes with digits and no separator — P2P, C2B, v2)
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_TIME = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_AUDIT_COUNT = re.compile(r"\(\d+ facts\)")
_AGENT_NAME = re.compile(r"\bAgents?\s[1-5](?:\s*[–‑-]\s*[1-5])?\b")
# Numbers carried inside identifiers as a quantity with a unit (30d, 5L, 48h):
# a narrative paraphrase ("30-day", "INR 5 L") is supported by them.
_UNIT_DIGITS = re.compile(r"(?<![0-9])(\d+)(?=[A-Za-z])")


ACTIONS = ("CLEAR", "MONITOR", "HUMAN_REVIEW", "ESCALATE", "BLOCK")
DECISION_LABELS = ("Recommended action", "Score band action")


def tokens(text: str, unit_numbers: bool = True) -> tuple[set[str], set[str], set[str], set[Decimal]]:
    """Return (identifiers, dates, times, numbers) found in text.

    ``unit_numbers`` adds digits carried inside identifiers (30 from 30d).
    Use True for fact text (they support a paraphrase) and False for
    statement text (the identifier itself is already checked).
    """
    t = _AGENT_NAME.sub(" ", _AUDIT_COUNT.sub(" ", text))
    t = FACT_REF.sub(" ", t)
    idents = set(_UUID.findall(t))
    t = _UUID.sub(" ", t)
    unit_nums: set[Decimal] = set()
    for m in _IDENT.findall(t):
        if any(ch.isdigit() for ch in m):
            idents.add(m.rstrip("."))
            unit_nums |= {Decimal(d).normalize() for d in _UNIT_DIGITS.findall(m)}
    t = _IDENT.sub(lambda m: " " if any(ch.isdigit() for ch in m.group(0)) else m.group(0), t)
    dates = set(_DATE.findall(t))
    t = _DATE.sub(" ", t)
    times = set(_TIME.findall(t))
    t = _TIME.sub(" ", t)
    nums: set[Decimal] = set(unit_nums) if unit_numbers else set()
    for raw in _NUMBER.findall(t):
        raw = raw.rstrip(",").replace(",", "")
        try:
            nums.add(Decimal(raw).normalize())
        except InvalidOperation:
            continue
    return idents, dates, times, nums


def fact_text(f: Fact) -> str:
    """Everything a statement may legitimately quote from a fact."""
    parts = [f.label, f.value, f.source_agent.value, f.source, f.source_mode or "", f.reference_id or "",
             f.source_field]
    if f.observed_at:
        # Formatted form only: its date and time are recognised as such, so the
        # raw ISO string's digits cannot leak out as "supported" numbers.
        parts.append(fmt_dt(f.observed_at))
    return " | ".join(parts)


def complete_identifier_citations(statement: Statement, bundle: EvidenceBundle,
                                  allowed_sections: tuple[ReportSection, ...]) -> Statement:
    """Add citations for identifiers the statement names but does not cite.

    Only identifiers are completed (an identifier names one entity, so the
    supporting fact is unambiguous). For each identifier absent from the cited
    facts, the first fact (bundle order, allowed sections) containing it is
    added. Numbers, dates and times are never completed. Added ids are
    recorded in ``added_fact_ids``.
    """
    by_id = {f.fact_id: f for f in bundle.facts}
    cited = " | ".join(fact_text(by_id[i]) for i in statement.fact_ids if i in by_id)
    added: list[str] = []
    for ident in sorted(tokens(statement.text)[0]):
        if ident in cited:
            continue
        for f in bundle.facts:
            if f.section in allowed_sections and f.fact_id not in statement.fact_ids \
                    and f.fact_id not in added and ident in f"{f.label} {f.value}":
                added.append(f.fact_id)
                cited += " | " + fact_text(f)
                break
    # Action names: complete only with the decision fact that states exactly
    # that action, so a wrong action stays ungrounded.
    for action in ACTIONS:
        if re.search(rf"\b{action}\b", statement.text) and not re.search(rf"\b{action}\b", cited):
            for f in bundle.facts:
                if f.label in DECISION_LABELS and f.value == action and f.fact_id not in statement.fact_ids \
                        and f.fact_id not in added:
                    added.append(f.fact_id)
                    cited += " | " + fact_text(f)
                    break
    if not added:
        return statement
    return statement.model_copy(update={"fact_ids": list(statement.fact_ids) + added,
                                        "added_fact_ids": list(statement.added_fact_ids) + added})
