"""
Sentinel AI — Phase 11 tests: Output Validator.

Each check is exercised with a deliberately broken report (it must fail) and
with its near-miss (it must pass), so the validator is shown to catch real
defects without flagging legitimate wording. Also covers grounding tokens,
Agent 5 citation completion and the validation stage (template fallback).
"""

from __future__ import annotations

import json

import pytest

from src.agents.agent5 import ExplanationGeneratorAgent, Generator, ReportSection, Statement, StatementOrigin
from src.agents.agent5.grounding import complete_identifier_citations, tokens
from src.agents.agent5.report_schema import LLM_SECTIONS
from src.agents.validator import CheckId, OutputValidator, ValidationStage, ValidationStatus
from tests.test_agent5_explanation_generator import FakeLLM, make_state, valid_llm_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def state():
    return make_state()


def template_report(state):
    return ExplanationGeneratorAgent(llm_client=None).generate(state)


def llm_report(state, responder=valid_llm_json):
    return ExplanationGeneratorAgent(llm_client=FakeLLM([responder])).generate(state)


def fact(report, label_prefix):
    return next(f for f in report.evidence_bundle.facts if f.label.startswith(label_prefix))


def add_statement(report, section, text, fact_ids, origin=StatementOrigin.LLM):
    secs = []
    for s in report.sections:
        if s.section == section:
            s = s.model_copy(update={"statements": list(s.statements)
                                     + [Statement(text=text, fact_ids=fact_ids, origin=origin)]})
        secs.append(s)
    return report.model_copy(update={"sections": secs})


def validate(state, report):
    return OutputValidator().validate(state, report)


def failed(v):
    return set(v.failed_checks())


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------

class TestBaseline:
    def test_template_report_validates(self, state):
        v = validate(state, template_report(state))
        assert v.status == ValidationStatus.VALIDATED, [i.reason for c in v.checks for i in c.issues]
        assert v.checks_passed == v.checks_total == len(CheckId)
        assert v.analyst_warning is None

    def test_wellformed_llm_report_validates(self, state):
        v = validate(state, llm_report(state))
        assert v.status == ValidationStatus.VALIDATED, [i.reason for c in v.checks for i in c.issues]

    def test_no_report(self, state):
        v = OutputValidator().validate(state, None)
        assert v.status == ValidationStatus.NEEDS_HUMAN_REVIEW
        assert CheckId.STRUCTURE in failed(v)

    def test_result_records_identity(self, state):
        r = template_report(state)
        v = validate(state, r)
        assert v.case_id == "CASE-TEST" and v.report_run_id == r.agent5_run_id
        assert v.bundle_hash == r.evidence_bundle.bundle_hash and v.report_generator == "TEMPLATE"


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

class TestStructure:
    def test_missing_section(self, state):
        r = template_report(state)
        r = r.model_copy(update={"sections": r.sections[:-1]})
        assert CheckId.STRUCTURE in failed(validate(state, r))

    def test_unknown_fact_id(self, state):
        r = add_statement(template_report(state), ReportSection.CASE_SUMMARY, "x", ["F-999"])
        assert CheckId.STRUCTURE in failed(validate(state, r))

    def test_missing_upstream_outputs(self):
        st = make_state(with_agents=False)
        v = validate(st, template_report(st))
        assert v.status == ValidationStatus.NEEDS_HUMAN_REVIEW and CheckId.STRUCTURE in failed(v)

    def test_added_ids_must_be_subset(self, state):
        r = template_report(state)
        bad = Statement(text="Case summary.", fact_ids=["F-001"], origin=StatementOrigin.LLM, added_fact_ids=["F-002"])
        secs = [s.model_copy(update={"statements": [bad] + list(s.statements)})
                if s.section == ReportSection.CASE_SUMMARY else s for s in r.sections]
        assert CheckId.STRUCTURE in failed(validate(state, r.model_copy(update={"sections": secs})))


class TestBundleIntegrity:
    def test_tampered_fact_breaks_hash(self, state):
        r = template_report(state)
        b = r.evidence_bundle
        facts = [f.model_copy(update={"value": "INR 9,999.00"}) if f.label == "Amount" else f for f in b.facts]
        r = r.model_copy(update={"evidence_bundle": b.model_copy(update={"facts": facts})})
        assert CheckId.BUNDLE_INTEGRITY in failed(validate(state, r))

    def test_bundle_from_different_state(self, state):
        r = template_report(state)
        other = make_state(case_id="CASE-OTHER")
        assert CheckId.BUNDLE_INTEGRITY in failed(validate(other, r))

    def test_audit_trail_must_cover_all_facts(self, state):
        r = template_report(state)
        secs = [s.model_copy(update={"statements": s.statements[:1]})
                if s.section == ReportSection.SOURCE_AUDIT_TRAIL else s for s in r.sections]
        assert CheckId.BUNDLE_INTEGRITY in failed(validate(state, r.model_copy(update={"sections": secs})))


class TestCitationGrounding:
    def test_invented_number(self, state):
        r = template_report(state)
        amt = fact(r, "Amount")
        bad = add_statement(r, ReportSection.CASE_SUMMARY, "The payment was INR 5,500.00.", [amt.fact_id])
        v = validate(state, bad)
        assert CheckId.CITATION_GROUNDING in failed(v)
        assert "5500" in v.check(CheckId.CITATION_GROUNDING).issues[0].reason

    def test_number_with_different_formatting_passes(self, state):
        r = template_report(state)
        amt = fact(r, "Amount")  # INR 5,000.00
        ok = add_statement(r, ReportSection.CASE_SUMMARY, "The payment was INR 5000.", [amt.fact_id])
        assert CheckId.CITATION_GROUNDING not in failed(validate(state, ok))

    def test_rounding_is_rejected(self, state):
        """Phase 10/11 finding: '270 minutes' written for a fact saying 270.1."""
        r = template_report(state)
        tx_fact = fact(r, "Transaction id")
        ok = add_statement(r, ReportSection.CASE_SUMMARY, "Elapsed 270.1 minutes.", [tx_fact.fact_id])
        assert CheckId.CITATION_GROUNDING in failed(validate(state, ok))  # not in the cited fact at all
        sig = fact(r, "Signal ANOMALY")  # "value 0.80, weight 0.30, contribution 0.240: ..."
        bad = add_statement(r, ReportSection.RECOMMENDED_ACTION, "The anomaly contribution was about 0.2.",
                            [sig.fact_id])
        assert CheckId.CITATION_GROUNDING in failed(validate(state, bad))
        exact = add_statement(r, ReportSection.RECOMMENDED_ACTION, "The anomaly contribution was 0.24.",
                              [sig.fact_id])
        assert CheckId.CITATION_GROUNDING not in failed(validate(state, exact))

    def test_metadata_numbers_do_not_support_claims(self, state):
        r = template_report(state)
        kyc = fact(r, "Sender KYC status")  # observed_at holds year/day/hour digits
        bad = add_statement(r, ReportSection.EVIDENCE_SUMMARY, "KYC was checked 21 times.", [kyc.fact_id])
        assert CheckId.CITATION_GROUNDING in failed(validate(state, bad))

    def test_identifier_not_in_cited_fact(self, state):
        r = template_report(state)
        amt = fact(r, "Amount")
        bad = add_statement(r, ReportSection.CASE_SUMMARY, "Account ACC_ZZZ_999 sent it.", [amt.fact_id])
        assert CheckId.CITATION_GROUNDING in failed(validate(state, bad))

    def test_date_not_in_cited_fact(self, state):
        r = template_report(state)
        amt = fact(r, "Amount")
        bad = add_statement(r, ReportSection.CASE_SUMMARY, "Sent on 2026-01-01.", [amt.fact_id])
        assert CheckId.CITATION_GROUNDING in failed(validate(state, bad))

    def test_correct_value_wrong_citation(self, state):
        """Phase 10 finding: a correct value cited against the wrong fact."""
        r = template_report(state)
        amt, kyc = fact(r, "Amount"), fact(r, "Sender KYC status")
        bad = add_statement(r, ReportSection.CASE_SUMMARY, f"The payment was {amt.value}.", [kyc.fact_id])
        assert CheckId.CITATION_GROUNDING in failed(validate(state, bad))


class TestDecisionConsistency:
    def test_decision_tampered(self, state):
        r = template_report(state)
        d = r.decision.model_copy(update={"recommended_action": "CLEAR"})
        assert CheckId.DECISION_CONSISTENCY in failed(validate(state, r.model_copy(update={"decision": d})))

    def test_wrong_action_in_narrative(self, state):
        r = template_report(state)
        actual = r.decision.recommended_action
        wrong = "BLOCK" if actual != "BLOCK" else "CLEAR"
        amt = fact(r, "Amount")
        bad = add_statement(r, ReportSection.RECOMMENDED_ACTION, f"The case should be {wrong}.", [amt.fact_id])
        assert CheckId.DECISION_CONSISTENCY in failed(validate(state, bad))

    @pytest.mark.parametrize("text,should_fail", [
        ("No SAR/STR filing is made automatically.", True),
        ("A SAR is not recommended for this case.", True),
        ("The override does not itself constitute a SAR filing.", False),
        ("The SAR/STR recommendation requires a qualified human decision.", False),
    ])
    def test_sar_wording_when_sar_recommended(self, text, should_fail):
        from tests.test_agent4_risk_assessor import NetworkPatternType, finding, make_a1, make_a3, make_tx
        st = make_state(tx=make_tx(is_new_device=True, is_new_beneficiary=True, ben_added_min=5),
                        a1=make_a1(0.95, 0.97),
                        a3=make_a3(findings=[finding(NetworkPatternType.LAYERING, 1.0)]))
        r = template_report(st)
        assert r.decision.sar_recommended  # fixture must reach a SAR recommendation
        sar = fact(r, "SAR/STR recommendation")
        v = validate(st, add_statement(r, ReportSection.RECOMMENDED_ACTION, text, [sar.fact_id]))
        assert (CheckId.DECISION_CONSISTENCY in failed(v)) is should_fail

    def test_sar_asserted_when_not_recommended(self, state):
        r = template_report(state)
        if r.decision.sar_recommended:
            pytest.skip("fixture recommends a SAR")
        sar = fact(r, "SAR/STR recommendation")
        bad = add_statement(r, ReportSection.RECOMMENDED_ACTION, "A SAR is recommended.", [sar.fact_id])
        assert CheckId.DECISION_CONSISTENCY in failed(validate(state, bad))


class TestRegulatory:
    def test_regulator_named_in_narrative(self, state):
        r = template_report(state)
        amt = fact(r, "Amount")
        bad = add_statement(r, ReportSection.CASE_SUMMARY, "Under FATF Recommendation 20 this must be reported.",
                            [amt.fact_id])
        assert CheckId.REGULATORY in failed(validate(state, bad))

    def test_unapproved_reference(self, state):
        r = template_report(state)
        reg = next(f for f in r.evidence_bundle.facts if f.section == ReportSection.REGULATORY_ASSESSMENT)
        bad = add_statement(r, ReportSection.REGULATORY_ASSESSMENT, "See RBI-FRM-3.4.2.", [reg.fact_id],
                            origin=StatementOrigin.SYSTEM)
        assert CheckId.REGULATORY in failed(validate(state, bad))

    def test_approved_matches_must_be_reported(self, state):
        r = template_report(state)
        if not r.decision.regulatory_reference_ids:
            pytest.skip("no regulatory matches in fixture")
        keep = [st for st in r.section(ReportSection.REGULATORY_ASSESSMENT).statements
                if not st.text.startswith("Regulatory reference")]
        secs = [s.model_copy(update={"statements": keep}) if s.section == ReportSection.REGULATORY_ASSESSMENT
                else s for s in r.sections]
        assert CheckId.REGULATORY in failed(validate(state, r.model_copy(update={"sections": secs})))


class TestLanguage:
    @pytest.mark.parametrize("text,should_fail", [
        ("This is confirmed fraud.", True),
        ("The account is a money mule.", True),
        ("The evidence proves that funds were laundered.", True),
        ("This is not a confirmed identification of a money mule.", False),
        ("The pattern is consistent with mule-like pass-through and requires review.", False),
    ])
    def test_conclusive_wording(self, state, text, should_fail):
        r = template_report(state)
        amt = fact(r, "Amount")
        v = validate(state, add_statement(r, ReportSection.NETWORK_ANALYSIS, text, [amt.fact_id]))
        assert (CheckId.LANGUAGE in failed(v)) is should_fail

    def test_only_llm_statements_checked(self, state):
        r = template_report(state)
        amt = fact(r, "Amount")
        v = validate(state, add_statement(r, ReportSection.NETWORK_ANALYSIS, "Confirmed fraud.", [amt.fact_id],
                                          origin=StatementOrigin.TEMPLATE))
        assert CheckId.LANGUAGE not in failed(v)


class TestLabelLeakage:
    def test_label_in_statement(self, state):
        r = template_report(state)
        amt = fact(r, "Amount")
        v = validate(state, add_statement(r, ReportSection.CASE_SUMMARY, "Dataset says FRAUDULENT.",
                                          [amt.fact_id]))
        assert CheckId.LABEL_LEAKAGE in failed(v)

    def test_labels_on_state_transaction(self, state):
        r = template_report(state)
        tx = state["transaction"]
        st = {**state, "transaction": tx.model_copy(update={"is_fraud": True})}
        assert CheckId.LABEL_LEAKAGE in failed(validate(st, r))


# ---------------------------------------------------------------------------
# Grounding tokens and citation completion
# ---------------------------------------------------------------------------

class TestTokens:
    def test_extraction(self):
        ids, dates, times, nums = tokens(
            "Account ACC_IND_000917 sent INR 1,050,368.45 via P2P at 2026-08-03 14:42:29 (rule AGENT3.LAYERING.v2)",
            unit_numbers=False)
        assert {"ACC_IND_000917", "P2P", "AGENT3.LAYERING.v2"} <= ids
        assert dates == {"2026-08-03"} and times == {"14:42:29"}
        assert [format(n, "f") for n in nums] == ["1050368.45"]

    def test_unit_numbers_support_paraphrase(self):
        assert 30 in {int(n) for n in tokens("amount_ratio_vs_30d_avg")[3]}
        assert not tokens("amount_ratio_vs_30d_avg", unit_numbers=False)[3]

    def test_agent_names_and_uuids_not_numbers(self):
        ids, _, _, nums = tokens("Agent 1 and Agents 1–4; ref 2980e8f3-c38b-406b-ac9e-f55c5f556ce8")
        assert not nums and "2980e8f3-c38b-406b-ac9e-f55c5f556ce8" in ids


class TestCitationCompletion:
    def test_adds_fact_for_named_identifier(self, state):
        r = template_report(state)
        b = r.evidence_bundle
        txid = fact(r, "Transaction id")  # T-001
        amt = fact(r, "Amount")
        st = Statement(text=f"Transaction {txid.value} moved {amt.value}.", fact_ids=[amt.fact_id],
                       origin=StatementOrigin.LLM)
        done = complete_identifier_citations(st, b, LLM_SECTIONS)
        assert txid.fact_id in done.fact_ids and done.added_fact_ids == [txid.fact_id]

    def test_never_completes_numbers(self, state):
        r = template_report(state)
        kyc = fact(r, "Sender KYC status")
        st = Statement(text="The payment was INR 5,000.00.", fact_ids=[kyc.fact_id], origin=StatementOrigin.LLM)
        assert complete_identifier_citations(st, r.evidence_bundle, LLM_SECTIONS).added_fact_ids == []

    def test_action_completed_only_when_it_matches(self, state):
        r = template_report(state)
        amt = fact(r, "Amount")
        actual = r.decision.recommended_action
        wrong = "BLOCK" if actual != "BLOCK" else "CLEAR"
        ok = complete_identifier_citations(
            Statement(text=f"Recommended: {actual}.", fact_ids=[amt.fact_id], origin=StatementOrigin.LLM),
            r.evidence_bundle, LLM_SECTIONS)
        assert ok.added_fact_ids
        no = complete_identifier_citations(
            Statement(text=f"Recommended: {wrong}.", fact_ids=[amt.fact_id], origin=StatementOrigin.LLM),
            r.evidence_bundle, LLM_SECTIONS)
        assert no.added_fact_ids == []

    def test_agent5_applies_completion_to_llm_output(self, state):
        def names_sender_without_citing_it(user):
            d = json.loads(valid_llm_json(user))
            d["sections"]["CASE_SUMMARY"][0]["text"] += " Transaction T-001."
            return json.dumps(d)
        r = llm_report(state, names_sender_without_citing_it)
        first = r.section(ReportSection.CASE_SUMMARY).statements[0]
        assert first.added_fact_ids and any("citation(s) added by code" in w for w in r.warnings)
        assert validate(state, r).status == ValidationStatus.VALIDATED


# ---------------------------------------------------------------------------
# Validation stage
# ---------------------------------------------------------------------------

def _bad_llm(user):
    d = json.loads(valid_llm_json(user))
    d["sections"]["NETWORK_ANALYSIS"][0]["text"] = "This is confirmed fraud of INR 123,456.78."
    return json.dumps(d)


class TestValidationStage:
    def test_valid_llm_report_presented(self, state):
        state["agent5_output"] = llm_report(state)
        out = ValidationStage()(state)
        assert out["validation_output"].status == ValidationStatus.VALIDATED
        assert out["agent5_output"].generator == Generator.LLM
        assert out["agent5_output"].validation_status == "VALIDATED"
        assert out["rejected_reports"] == []

    def test_failed_llm_report_replaced_by_validated_template(self, state):
        llm = llm_report(state, _bad_llm)
        state["agent5_output"] = llm
        out = ValidationStage()(state)
        presented = out["agent5_output"]
        assert presented.generator == Generator.TEMPLATE and presented.validation_status == "VALIDATED"
        assert presented.evidence_bundle.bundle_hash == llm.evidence_bundle.bundle_hash  # same evidence
        assert "LLM report failed validation" in presented.fallback_reason
        [rej] = out["rejected_reports"]
        assert rej.report.agent5_run_id == llm.agent5_run_id
        assert rej.report.validation_status == "NEEDS_HUMAN_REVIEW"
        assert {CheckId.LANGUAGE, CheckId.CITATION_GROUNDING} <= set(rej.validation.failed_checks())

    def test_fallback_can_be_disabled(self, state):
        state["agent5_output"] = llm_report(state, _bad_llm)
        out = ValidationStage(template_fallback=False)(state)
        assert out["validation_output"].status == ValidationStatus.NEEDS_HUMAN_REVIEW
        assert out["agent5_output"].validation_status == "NEEDS_HUMAN_REVIEW"
        assert out["agent5_output"].warnings[-1].startswith("Report NOT validated")

    def test_template_report_failure_flags_case(self):
        st = make_state(with_agents=False)
        st["agent5_output"] = template_report(st)
        out = ValidationStage()(st)
        assert out["validation_output"].status == ValidationStatus.NEEDS_HUMAN_REVIEW
        assert out["agent5_output"].validation_status == "NEEDS_HUMAN_REVIEW"
        assert out["rejected_reports"] == []

    def test_deterministic(self, state):
        r = template_report(state)
        a, b = validate(state, r), validate(state, r)
        strip = lambda v: v.model_dump(exclude={"validation_run_id", "validated_at_utc"})  # noqa: E731
        assert strip(a) == strip(b)
