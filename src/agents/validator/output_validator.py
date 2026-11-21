"""
Sentinel AI — Output Validator (Phase 11).

Deterministic checks of an Agent 5 report against its evidence bundle, the
case state and the Risk Assessor (Agent 4). No LLM is involved.

Checks (all required):
  STRUCTURE             seven sections in order, non-empty; citations exist;
                        no upstream output missing
  BUNDLE_INTEGRITY      hash recomputes; bundle == fresh rebuild from state;
                        every fact sourced; audit trail cites every fact
  CITATION_GROUNDING    identifiers, dates, times and numbers in a statement
                        appear in the facts it cites
  DECISION_CONSISTENCY  decision == Agent 4; decision statement matches;
                        narrative action names / SAR wording agree
  REGULATORY            references == Agent 4 approved matches; narrative
                        names no regulation / regulator
  LANGUAGE              no conclusive / accusatory wording in the narrative
  LABEL_LEAKAGE         no dataset ground-truth label in report or evidence

Limits: the validator checks that every concrete token is supported by a cited
fact. It cannot detect a statement that combines supported tokens with a
wrong meaning; that remains an analyst-review responsibility.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Iterable, Optional

from ..agent5.facts import build_evidence_bundle
from ..agent5.grounding import FACT_REF as _FACT_REF
from ..agent5.grounding import fact_text as _fact_text
from ..agent5.grounding import tokens as _tokens
from ..agent5.report_schema import (
    SECTION_TITLES,
    Agent5Output,
    Fact,
    ReportSection,
    Statement,
    StatementOrigin,
)
from .schema import (
    CHECK_DESCRIPTIONS,
    CheckId,
    CheckResult,
    StatementIssue,
    ValidationOutput,
    ValidationStatus,
)

MAX_ISSUES_PER_CHECK = 25

# --------------------------------------------------------------------------
# Token extraction
# --------------------------------------------------------------------------

from ..agent5.grounding import ACTIONS as _ACTIONS  # noqa: E402


# --------------------------------------------------------------------------
# Language rules (narrative only)
# --------------------------------------------------------------------------

_CONCLUSIVE = [
    r"confirmed (?:case of )?(?:fraud|money[- ]laundering|mule)",
    r"\bis (?:a|an) (?:money )?mule\b",
    r"\b(?:proves?|proven|proof of)\b",
    r"\bguilty\b", r"\bcriminal\b", r"\bfraudster\b",
    r"\blaundered\b", r"\bcommitted (?:fraud|a crime)\b",
    r"\bis (?:clearly |definitely |certainly )?fraudulent\b",
    r"\bdefinitely\b", r"\bundoubtedly\b", r"\bwithout (?:a )?doubt\b",
]
_NEGATION_WINDOW = re.compile(r"\b(?:not|no|never|without|nor)\b[^.;]{0,25}$", re.I)

_REGULATORY_TERMS = [
    r"\bFATF\b", r"\bRBI\b", r"\bReserve Bank\b", r"\bPMLA\b", r"\bFIU(?:-IND)?\b", r"\bFinCEN\b",
    r"\bPrevention of Money[- ]Laundering\b", r"\bRecommendation \d+\b", r"\bMaster Direction",
    r"\bregulation\b", r"\bregulatory (?:requirement|obligation)",
]
_REF_ID = re.compile(r"\b(?:FATF|RBI)-[A-Za-z0-9.\-]+\b")

# Explicit statements that no SAR/STR is recommended / needed. (A sentence such
# as "the override does not itself constitute a SAR filing" is not a contradiction.)
_SAR_NEGATED = [
    r"\bno (?:SAR|STR)\b",
    r"\bwithout (?:a |an )?(?:SAR|STR)\b",
    r"\b(?:SAR|STR)\b[^.;]{0,30}\bnot (?:recommended|required|warranted|needed|suggested|advised)\b",
    r"\bnot (?:recommend|require|warrant|suggest|advise)\w*\b[^.;]{0,20}\b(?:SAR|STR)\b",
]
_SAR_ASSERTED = re.compile(r"\b(?:SAR|STR)\b[^.;]{0,40}\b(?:recommended|suggested|warranted|advised)\b", re.I)

_LABEL_PATTERNS = [
    r"\bFRAUDULENT\b", r"\bLEGITIMATE\b", r"\bBORDERLINE\b", r"\bSCENARIO_\d+", r"\bMULE_SUSPECT\b",
    r"\bis_fraud\b", r"\brisk_label\b", r"\bscenario_id\b",
]


def _hits(patterns: Iterable[str], text: str, *, negation_aware: bool = False, flags=re.I) -> list[str]:
    out = []
    for p in patterns:
        for m in re.finditer(p, text, flags):
            if negation_aware and _NEGATION_WINDOW.search(text[:m.start()]):
                continue
            out.append(m.group(0))
    return out


# --------------------------------------------------------------------------
# Validator
# --------------------------------------------------------------------------

class OutputValidator:
    """Validate an Agent 5 report. Pure and deterministic; never raises."""

    def validate(self, state: dict, report: Optional[Agent5Output] = None) -> ValidationOutput:
        report = report if report is not None else state.get("agent5_output")
        tx = state.get("transaction")
        base = dict(case_id=state.get("case_id"), transaction_id=getattr(tx, "raw_record_id", None))
        if report is None:
            return self._result(base, None, [CheckResult(
                check=CheckId.STRUCTURE, description=CHECK_DESCRIPTIONS[CheckId.STRUCTURE], passed=False,
                issues=[StatementIssue(check=CheckId.STRUCTURE, reason="No report to validate.")])])
        checks: list[CheckResult] = []
        for fn in (self._structure, self._bundle_integrity, self._grounding, self._decision,
                   self._regulatory, self._language, self._leakage):
            try:
                checks.append(fn(state, report))
            except Exception as exc:  # noqa: BLE001 — a crashing check is a failed check
                cid = _CHECK_OF[fn.__name__]
                checks.append(CheckResult(check=cid, description=CHECK_DESCRIPTIONS[cid], passed=False,
                                          issues=[StatementIssue(check=cid, reason=f"Check error: {type(exc).__name__}")]))
        return self._result(base, report, checks)

    # ------------------------------------------------------------------

    @staticmethod
    def _result(base: dict, report: Optional[Agent5Output], checks: list[CheckResult]) -> ValidationOutput:
        ok = all(c.passed for c in checks) and len(checks) == len(CheckId)
        failed = [c.check.value for c in checks if not c.passed]
        return ValidationOutput(
            **base,
            report_run_id=getattr(report, "agent5_run_id", None),
            report_generator=getattr(getattr(report, "generator", None), "value", None),
            bundle_hash=getattr(getattr(report, "evidence_bundle", None), "bundle_hash", None),
            status=ValidationStatus.VALIDATED if ok else ValidationStatus.NEEDS_HUMAN_REVIEW,
            checks=checks,
            checks_passed=sum(c.passed for c in checks),
            checks_total=len(CheckId),
            analyst_warning=None if ok else (
                "Report NOT validated (failed: " + ", ".join(failed) + "). It must not be relied on "
                "without analyst review of the cited evidence."),
        )

    @staticmethod
    def _make(cid: CheckId, issues: list[StatementIssue], n: int) -> CheckResult:
        return CheckResult(check=cid, description=CHECK_DESCRIPTIONS[cid], passed=not issues,
                           items_checked=n, issues=issues[:MAX_ISSUES_PER_CHECK])

    @staticmethod
    def _statements(report: Agent5Output, origins: Optional[set] = None):
        for sec in report.sections:
            for i, st in enumerate(sec.statements):
                if origins is None or st.origin in origins:
                    yield sec, i, st

    @staticmethod
    def _issue(cid: CheckId, sec, i: int, st: Statement, reason: str) -> StatementIssue:
        return StatementIssue(check=cid, section=sec.section.value, statement_index=i,
                              origin=st.origin.value, text=st.text[:300], reason=reason)

    # ---- STRUCTURE -------------------------------------------------------

    def _structure(self, state: dict, report: Agent5Output) -> CheckResult:
        cid, issues = CheckId.STRUCTURE, []
        if report.evidence_bundle is None:
            issues.append(StatementIssue(check=cid, reason=f"Report has no evidence bundle (status {report.status.value})."))
            return self._make(cid, issues, 0)
        order = [s.section for s in report.sections]
        if order != list(ReportSection):
            issues.append(StatementIssue(check=cid, reason="Sections missing or out of order: "
                                         + ", ".join(s.value for s in order)))
        for sec in report.sections:
            if sec.title != SECTION_TITLES[sec.section]:
                issues.append(StatementIssue(check=cid, section=sec.section.value, reason=f"Unexpected title {sec.title!r}."))
            if not sec.statements:
                issues.append(StatementIssue(check=cid, section=sec.section.value, reason="Section is empty."))
        ids = report.evidence_bundle.ids()
        n = 0
        for sec, i, st in self._statements(report):
            n += 1
            if not st.fact_ids:
                issues.append(self._issue(cid, sec, i, st, "Statement cites no facts."))
            unknown = [f for f in st.fact_ids if f not in ids]
            if unknown:
                issues.append(self._issue(cid, sec, i, st, "Cites unknown facts: " + ", ".join(unknown)))
            if not set(st.added_fact_ids) <= set(st.fact_ids):
                issues.append(self._issue(cid, sec, i, st, "added_fact_ids not a subset of fact_ids."))
            if st.added_fact_ids and st.origin != StatementOrigin.LLM:
                issues.append(self._issue(cid, sec, i, st, "Citation completion applied to a non-LLM statement."))
            mentioned = [m for m in _FACT_REF.findall(st.text) if m not in ids]
            if mentioned:
                issues.append(self._issue(cid, sec, i, st, "Text names unknown facts: " + ", ".join(mentioned)))
        if report.evidence_bundle.missing_inputs:
            issues.append(StatementIssue(check=cid, reason="Upstream outputs missing: "
                                         + ", ".join(report.evidence_bundle.missing_inputs)))
        return self._make(cid, issues, n)

    # ---- BUNDLE_INTEGRITY ------------------------------------------------

    def _bundle_integrity(self, state: dict, report: Agent5Output) -> CheckResult:
        cid, issues = CheckId.BUNDLE_INTEGRITY, []
        b = report.evidence_bundle
        if b is None:
            return self._make(cid, [StatementIssue(check=cid, reason="No evidence bundle.")], 0)
        payload = json.dumps([f.model_dump(mode="json") for f in b.facts], sort_keys=True, ensure_ascii=False)
        if hashlib.sha256(payload.encode("utf-8")).hexdigest() != b.bundle_hash:
            issues.append(StatementIssue(check=cid, reason="Bundle hash does not match its facts."))
        expected = [f"F-{i:03d}" for i in range(1, len(b.facts) + 1)]
        if [f.fact_id for f in b.facts] != expected:
            issues.append(StatementIssue(check=cid, reason="Fact ids are not sequential and unique."))
        fresh = build_evidence_bundle(state)
        if fresh.facts != b.facts:
            diff = next((f"{x.fact_id} ({x.label})" for x, y in zip(b.facts, fresh.facts) if x != y),
                        f"fact count {len(b.facts)} vs {len(fresh.facts)}")
            issues.append(StatementIssue(check=cid, reason=f"Bundle differs from the case state (first difference: {diff})."))
        if b.case_id != state.get("case_id"):
            issues.append(StatementIssue(check=cid, reason="Bundle case id differs from the case."))
        for f in b.facts:
            if not (f.source and f.source_field and f.value):
                issues.append(StatementIssue(check=cid, reason=f"{f.fact_id} lacks a source, field or value."))
        audit = report.section(ReportSection.SOURCE_AUDIT_TRAIL)
        cited = {i for st in (audit.statements if audit else []) for i in st.fact_ids}
        missing = sorted(b.ids() - cited)
        if missing:
            issues.append(StatementIssue(check=cid, reason=f"Audit trail does not cite {len(missing)} fact(s): "
                                         + ", ".join(missing[:10])))
        return self._make(cid, issues, len(b.facts))

    # ---- CITATION_GROUNDING ---------------------------------------------

    def _grounding(self, state: dict, report: Agent5Output) -> CheckResult:
        cid, issues = CheckId.CITATION_GROUNDING, []
        b = report.evidence_bundle
        if b is None:
            return self._make(cid, [StatementIssue(check=cid, reason="No evidence bundle.")], 0)
        facts = {f.fact_id: f for f in b.facts}
        cache: dict[str, tuple] = {}
        n = 0
        for sec, i, st in self._statements(report):
            n += 1
            cited = [facts[x] for x in st.fact_ids if x in facts]
            text = " | ".join(_fact_text(f) for f in cited)
            if text not in cache:
                cache[text] = _tokens(text)
            f_nums = cache[text][3]
            s_ids, s_dates, s_times, s_nums = _tokens(st.text, unit_numbers=False)
            problems = []
            bad_ids = sorted(x for x in s_ids if x not in text)
            if bad_ids:
                problems.append("identifiers not in cited facts: " + ", ".join(bad_ids[:5]))
            bad_dates = sorted(d for d in s_dates if d not in text)
            if bad_dates:
                problems.append("dates not in cited facts: " + ", ".join(bad_dates[:5]))
            bad_times = sorted(t for t in s_times if t not in text and t.zfill(5) not in text)
            if bad_times:
                problems.append("times not in cited facts: " + ", ".join(bad_times[:5]))
            bad_nums = sorted((x for x in s_nums if x not in f_nums), key=lambda d: (float(d)))
            if bad_nums:
                problems.append("numbers not in cited facts: " + ", ".join(format(x, "f") for x in bad_nums[:6]))
            if problems:
                issues.append(self._issue(cid, sec, i, st, "; ".join(problems)))
        return self._make(cid, issues, n)

    # ---- DECISION_CONSISTENCY -------------------------------------------

    def _decision(self, state: dict, report: Agent5Output) -> CheckResult:
        from ..agent5.explanation_generator import decision_from_agent4

        cid, issues = CheckId.DECISION_CONSISTENCY, []
        expected = decision_from_agent4(state.get("agent4_output"))
        if report.decision != expected:
            diffs = [k for k in type(expected).model_fields if getattr(expected, k) != getattr(report.decision, k)]
            issues.append(StatementIssue(check=cid, reason="Decision differs from the Risk Assessor: " + ", ".join(diffs)))
        ra = report.section(ReportSection.RECOMMENDED_ACTION)
        if expected.recommended_action is not None:
            first = ra.statements[0] if ra and ra.statements else None
            if first is None or first.origin != StatementOrigin.SYSTEM \
                    or f"Recommended action: {expected.recommended_action}." not in first.text:
                issues.append(StatementIssue(check=cid, section=ReportSection.RECOMMENDED_ACTION.value,
                                             reason="Decision statement missing or does not match the Risk Assessor."))
            elif expected.risk_score is not None and f"{expected.risk_score:.2f}" not in first.text:
                issues.append(StatementIssue(check=cid, section=ReportSection.RECOMMENDED_ACTION.value,
                                             reason="Decision statement risk score does not match."))
        facts = {f.fact_id: f for f in (report.evidence_bundle.facts if report.evidence_bundle else [])}
        n = 0
        for sec, i, st in self._statements(report, {StatementOrigin.LLM}):
            n += 1
            cited = " ".join(_fact_text(facts[x]) for x in st.fact_ids if x in facts)
            for a in _ACTIONS:
                if re.search(rf"\b{a}\b", st.text) and not re.search(rf"\b{a}\b", cited):
                    issues.append(self._issue(cid, sec, i, st, f"Action {a} named without a cited fact stating it."))
            if expected.sar_recommended is True and _hits(_SAR_NEGATED, st.text):
                issues.append(self._issue(cid, sec, i, st, "Negated SAR/STR wording while a SAR/STR is recommended."))
            if expected.sar_recommended is False and _SAR_ASSERTED.search(st.text) \
                    and not _hits(_SAR_NEGATED, st.text):
                issues.append(self._issue(cid, sec, i, st, "SAR/STR described as recommended while it is not."))
        return self._make(cid, issues, n)

    # ---- REGULATORY ------------------------------------------------------

    def _regulatory(self, state: dict, report: Agent5Output) -> CheckResult:
        cid, issues = CheckId.REGULATORY, []
        a4 = state.get("agent4_output")
        approved = sorted({m.reference_id for m in a4.regulatory_matches}) if a4 is not None else []
        mentioned: set[str] = set()
        n = 0
        for sec, i, st in self._statements(report):
            n += 1
            refs = set(_REF_ID.findall(st.text))
            mentioned |= refs
            extra = sorted(refs - set(approved))
            if extra:
                issues.append(self._issue(cid, sec, i, st, "Reference not among approved matches: " + ", ".join(extra)))
            if st.origin == StatementOrigin.LLM:
                terms = _hits(_REGULATORY_TERMS, st.text)
                if terms:
                    issues.append(self._issue(cid, sec, i, st, "Narrative names regulation/regulator: "
                                              + ", ".join(sorted(set(terms)))))
            elif sec.section != ReportSection.REGULATORY_ASSESSMENT and refs:
                issues.append(self._issue(cid, sec, i, st, "Regulatory reference outside the regulatory section."))
        reg = report.section(ReportSection.REGULATORY_ASSESSMENT)
        in_section = {r for st in (reg.statements if reg else []) for r in _REF_ID.findall(st.text)}
        missing = sorted(set(approved) - in_section)
        if missing:
            issues.append(StatementIssue(check=cid, section=ReportSection.REGULATORY_ASSESSMENT.value,
                                         reason="Approved matches not reported: " + ", ".join(missing)))
        if sorted(report.decision.regulatory_reference_ids) != approved:
            issues.append(StatementIssue(check=cid, reason="Decision regulatory ids differ from approved matches."))
        if reg and any(st.origin == StatementOrigin.LLM for st in reg.statements):
            issues.append(StatementIssue(check=cid, section=ReportSection.REGULATORY_ASSESSMENT.value,
                                         reason="Regulatory section contains LLM-written statements."))
        return self._make(cid, issues, n)

    # ---- LANGUAGE --------------------------------------------------------

    def _language(self, state: dict, report: Agent5Output) -> CheckResult:
        cid, issues, n = CheckId.LANGUAGE, [], 0
        for sec, i, st in self._statements(report, {StatementOrigin.LLM}):
            n += 1
            hits = _hits(_CONCLUSIVE, st.text, negation_aware=True)
            if hits:
                issues.append(self._issue(cid, sec, i, st, "Conclusive wording: " + ", ".join(sorted(set(hits)))))
        return self._make(cid, issues, n)

    # ---- LABEL_LEAKAGE ---------------------------------------------------

    def _leakage(self, state: dict, report: Agent5Output) -> CheckResult:
        cid, issues = CheckId.LABEL_LEAKAGE, []
        texts = [("statement", st.text) for _, _, st in self._statements(report)]
        if report.evidence_bundle is not None:
            texts += [(f.fact_id, f"{f.label} {f.value}") for f in report.evidence_bundle.facts]
        for where, t in texts:
            hits = _hits(_LABEL_PATTERNS, t, flags=0)
            if hits:
                issues.append(StatementIssue(check=cid, reason=f"Label text in {where}: " + ", ".join(sorted(set(hits)))))
        tx = state.get("transaction")
        if tx is not None and (tx.is_fraud is not None or getattr(tx.metadata, "risk_label", None)
                               or getattr(tx.metadata, "scenario_id", None)):
            issues.append(StatementIssue(check=cid, reason="Case transaction still carries ground-truth fields."))
        return self._make(cid, issues, len(texts))


_CHECK_OF = {
    "_structure": CheckId.STRUCTURE, "_bundle_integrity": CheckId.BUNDLE_INTEGRITY,
    "_grounding": CheckId.CITATION_GROUNDING, "_decision": CheckId.DECISION_CONSISTENCY,
    "_regulatory": CheckId.REGULATORY, "_language": CheckId.LANGUAGE, "_leakage": CheckId.LABEL_LEAKAGE,
}


def validate_report(state: dict, report: Optional[Agent5Output] = None) -> ValidationOutput:
    return OutputValidator().validate(state, report)


__all__ = ["OutputValidator", "validate_report"]
