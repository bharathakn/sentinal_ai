"""
Sentinel AI — Agent 4 (Risk Assessor) tests.

Covers:
  - Agent4Config validation (weights, bands, night window)
  - Regulatory mapping registry integrity + verbatim provenance of excerpts
  - Each signal extractor, including unavailable / failed evidence
  - Score reproducibility and renormalisation over available evidence
  - Action bands and overrides (sanctions match, sanctions failure, low coverage)
  - Confidence levels, SAR recommendation, regulatory matches, unmapped triggers
  - LangGraph-compatible __call__ and error handling

All inputs are constructed in-memory; no database or network is required.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

import pytest

from src.agents.agent1.output_schema import Agent1Output, AgentStatus
from src.agents.agent2.output_schema import Agent2Output, Agent2Status, ProviderResult
from src.agents.agent3.output_schema import (
    Agent3Output,
    Agent3Status,
    NetworkFinding,
    NetworkPatternType,
)
from src.agents.agent4 import (
    Agent4Config,
    Agent4Output,
    Agent4Status,
    ConfidenceLevel,
    RecommendedAction,
    RiskAssessorAgent,
    RiskSignal,
)
from src.agents.agent4 import signals as sg
from src.agents.agent4.regulatory_mapping import (
    MAPPINGS,
    REFERENCES,
    RegulatoryTrigger,
    VerificationStatus,
    mappings_for,
)
from src.evidence.schemas import (
    AccountStats,
    BeneficiaryData,
    BeneficiaryResponse,
    CoreBankingData,
    CoreBankingResponse,
    DeviceRegistryData,
    DeviceRegistryResponse,
    EvidenceStatus,
    GeolocationData,
    GeolocationResponse,
    KYCData,
    KYCResponse,
    SanctionsData,
    SanctionsResponse,
    SourceMode,
)
from src.schemas.canonical_transaction import (
    AccountInfo,
    CanonicalTransaction,
    DataSource,
    DeviceInfo,
    TransactionChannel,
    TransactionMetadata,
    TransactionStatus,
)

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 8, 15, 6, 0, tzinfo=timezone.utc)
REPO = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def make_tx(
    hour: Optional[int] = 11,
    is_new_device: Optional[bool] = None,
    is_new_beneficiary: Optional[bool] = None,
    ben_added_min: Optional[int] = None,
    tz=IST,
) -> CanonicalTransaction:
    return CanonicalTransaction(
        raw_record_id="T-001",
        source_dataset=DataSource.MOCK_BANKING,
        timestamp=None if hour is None else datetime(2026, 8, 15, hour, 30, tzinfo=tz),
        amount=Decimal("5000.00"),
        currency="INR",
        channel=TransactionChannel.UPI,
        status=TransactionStatus.SUCCESS,
        sender=AccountInfo(account_id="ACC_S", account_name="Sender (SYNTHETIC)"),
        receiver=AccountInfo(account_id="ACC_R"),
        device=DeviceInfo(device_id="DEV_1", is_new_device=is_new_device),
        metadata=TransactionMetadata(
            is_new_beneficiary=is_new_beneficiary,
            time_since_beneficiary_added_min=ben_added_min,
        ),
    )


def make_a1(combined: Optional[float] = 0.1, xgb: Optional[float] = 0.1,
            status: AgentStatus = AgentStatus.COMPLETE) -> Agent1Output:
    return Agent1Output(
        transaction_id="T-001", source_dataset="MOCK_BANKING", scored_at_utc=NOW,
        status=status, anomaly_score=xgb, isolation_score=0.4,
        combined_confidence=combined,
    )


def _resp(cls, source, status=EvidenceStatus.FOUND, data=None, entity="ACC_S"):
    return cls(source=source, source_mode=SourceMode.MOCK, status=status,
               requested_entity_id=entity, retrieved_at=NOW, data=data)


def device(registered=True, status=EvidenceStatus.FOUND):
    data = None
    if status == EvidenceStatus.FOUND:
        data = DeviceRegistryData(
            device_id="DEV_1", account_id="ACC_S",
            registration_status="REGISTERED" if registered else "NOT_REGISTERED",
            is_registered_to_account=registered)
    return _resp(DeviceRegistryResponse, "MOCK_DEVICE", status, data)


def beneficiary(prev_fraud=False, known_tx=10, age_days=400, status=EvidenceStatus.FOUND):
    data = None
    if status == EvidenceStatus.FOUND:
        data = BeneficiaryData(account_id="ACC_R", account_age_days=age_days,
                               known_transaction_count=known_tx,
                               previous_fraud_flag=prev_fraud)
    return _resp(BeneficiaryResponse, "MOCK_BENEFICIARY", status, data, "ACC_R")


def core_banking(known=("ACC_R",)):
    stats = AccountStats(num_transactions_30d=10, avg_debit_amount_inr=1000.0,
                         max_debit_30d_inr=5000.0, known_beneficiaries=list(known),
                         tx_frequency_per_week=3.0, computation_note="test")
    return _resp(CoreBankingResponse, "MOCK_CORE_BANKING", data=CoreBankingData(
        account_id="ACC_S", stats=stats))


def kyc(status="VERIFIED", pep=False):
    return _resp(KYCResponse, "MOCK_KYC", data=KYCData(
        account_id="ACC_S", kyc_status=status, pep=pep))


def sanction(matched: Optional[bool], status: Optional[EvidenceStatus] = None):
    if status is None:
        status = EvidenceStatus.MATCH_FOUND if matched else EvidenceStatus.NO_MATCH
    data = None
    if matched is not None:
        data = SanctionsData(subject_query="q", matched=matched,
                             list_name="SYNTHETIC_WATCHLIST_MOCK" if matched else None,
                             match_confidence="HIGH" if matched else None,
                             matching_method="EXACT_NAME")
    return _resp(SanctionsResponse, "MOCK_SANCTIONS", status, data)


def geo(anomalous: Optional[bool] = False):
    return _resp(GeolocationResponse, "MOCK_GEOLOCATION", data=GeolocationData(
        account_id="ACC_S", distance_km=5000.0 if anomalous else 3.0,
        is_anomalous=anomalous))


_UNSET = object()


def make_a2(
    device_r=_UNSET, beneficiary_r=_UNSET, core_r=_UNSET, kyc_r=_UNSET,
    subj=_UNSET, acct=_UNSET, geo_r=_UNSET,
    provider_status: Optional[dict[str, EvidenceStatus]] = None,
    status: Agent2Status = Agent2Status.COMPLETE,
) -> Agent2Output:
    pick = lambda v, d: d if v is _UNSET else v  # noqa: E731
    subj_r = pick(subj, sanction(False))
    acct_r = pick(acct, sanction(False))
    ps = {
        "SANCTIONS_SUBJECT": subj_r.status if subj_r is not None else EvidenceStatus.PROVIDER_ERROR,
        "SANCTIONS_ACCOUNT": acct_r.status if acct_r is not None else EvidenceStatus.PROVIDER_ERROR,
    }
    ps.update(provider_status or {})
    return Agent2Output(
        transaction_id="T-001",
        status=status,
        core_banking=pick(core_r, core_banking()),
        kyc=pick(kyc_r, kyc()),
        device=pick(device_r, device()),
        beneficiary=pick(beneficiary_r, beneficiary()),
        sanctions_subject=subj_r,
        sanctions_account=acct_r,
        geolocation=pick(geo_r, geo(False)),
        provider_results=[ProviderResult(provider_name=k, status=v) for k, v in ps.items()],
    )


def finding(pattern=NetworkPatternType.MULE_LIKE, score: Optional[float] = 0.8):
    return NetworkFinding(pattern_type=pattern, rule_id=f"A3-{pattern.value}",
                          subject_account_id="ACC_R", heuristic_score=score,
                          explanation="test finding")


def make_a3(status=Agent3Status.COMPLETE, findings=()) -> Agent3Output:
    return Agent3Output(transaction_id="T-001", status=status,
                        findings=list(findings), finding_count=len(findings))


def assess(tx=None, a1=_UNSET, a2=_UNSET, a3=_UNSET, cfg=None) -> Agent4Output:
    agent = RiskAssessorAgent(cfg)
    return agent.assess(
        transaction=tx or make_tx(),
        agent1_output=make_a1() if a1 is _UNSET else a1,
        agent2_output=make_a2() if a2 is _UNSET else a2,
        agent3_output=make_a3() if a3 is _UNSET else a3,
    )


def row(out: Agent4Output, sig: RiskSignal):
    return next(b for b in out.score_breakdown if b.signal == sig)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestConfig:
    def test_default_weights_cover_all_signals_and_sum_to_one(self):
        cfg = Agent4Config()
        assert set(cfg.weights) == set(RiskSignal)
        assert sum(cfg.weights.values()) == pytest.approx(1.0)

    def test_default_is_marked_proposed(self):
        cfg = Agent4Config()
        assert "proposed" in cfg.config_version
        assert cfg.approval_status.startswith("PROPOSED")

    def test_weights_must_sum_to_one(self):
        w = dict(Agent4Config().weights)
        w[RiskSignal.ANOMALY] = 0.9
        with pytest.raises(ValueError, match="sum to 1.0"):
            Agent4Config(weights=w)

    def test_weights_must_cover_every_signal(self):
        w = dict(Agent4Config().weights)
        del w[RiskSignal.UNUSUAL_TIMING]
        with pytest.raises(ValueError, match="missing"):
            Agent4Config(weights=w)

    def test_negative_weight_rejected(self):
        w = dict(Agent4Config().weights)
        w[RiskSignal.ANOMALY] = -0.1
        w[RiskSignal.NETWORK_RISK] += 0.4
        with pytest.raises(ValueError):
            Agent4Config(weights=w)

    @pytest.mark.parametrize("m,e,b", [(50, 25, 75), (25, 50, 101), (0, 50, 75), (25, 25, 75)])
    def test_band_thresholds_must_ascend(self, m, e, b):
        with pytest.raises(ValueError):
            Agent4Config(monitor_threshold=m, escalate_threshold=e, block_threshold=b)

    def test_weights_are_immutable(self):
        cfg = Agent4Config()
        with pytest.raises(TypeError):
            cfg.weights[RiskSignal.ANOMALY] = 1.0  # type: ignore[index]

    def test_supplied_dict_is_frozen_copy(self):
        w = dict(Agent4Config().weights)
        cfg = Agent4Config(weights=w)
        w[RiskSignal.ANOMALY] = 0.99
        assert cfg.weights[RiskSignal.ANOMALY] == 0.30

    @pytest.mark.parametrize("score,action", [
        (0, RecommendedAction.CLEAR), (24.99, RecommendedAction.CLEAR),
        (25, RecommendedAction.MONITOR), (49.99, RecommendedAction.MONITOR),
        (50, RecommendedAction.ESCALATE), (74.99, RecommendedAction.ESCALATE),
        (75, RecommendedAction.BLOCK), (100, RecommendedAction.BLOCK),
    ])
    def test_action_bands(self, score, action):
        assert Agent4Config().action_for_score(score) == action

    @pytest.mark.parametrize("hour,night", [(22, False), (23, True), (0, True),
                                            (5, True), (6, False), (12, False)])
    def test_night_window_wraps_midnight(self, hour, night):
        assert Agent4Config().is_night_hour(hour) is night

    def test_non_wrapping_night_window(self):
        cfg = Agent4Config(night_start_hour=1, night_end_hour=4)
        assert cfg.is_night_hour(2) and not cfg.is_night_hour(4) and not cfg.is_night_hour(0)

    def test_audit_dict_contains_weights(self):
        d = Agent4Config().as_audit_dict()
        assert d["weights"]["ANOMALY"] == 0.30
        assert d["config_version"] == "0.1.0-proposed"


# ---------------------------------------------------------------------------
# Regulatory mapping registry
# ---------------------------------------------------------------------------

class TestRegulatoryRegistry:
    def test_every_mapping_references_known_reference(self):
        for m in MAPPINGS:
            assert m.reference_id in REFERENCES

    def test_mapping_ids_unique(self):
        ids = [m.mapping_id for m in MAPPINGS]
        assert len(ids) == len(set(ids))

    def test_all_references_unverified_pending_review(self):
        assert all(r.verification_status == VerificationStatus.UNVERIFIED
                   for r in REFERENCES.values())

    def test_rbi_references_carry_withdrawn_caveat(self):
        for r in REFERENCES.values():
            if r.organization == "RBI":
                assert any("Withdrawn" in c for c in r.caveats)

    @pytest.mark.parametrize("trigger", [
        RegulatoryTrigger.NEW_DEVICE, RegulatoryTrigger.NEW_BENEFICIARY,
        RegulatoryTrigger.UNUSUAL_TIMING, RegulatoryTrigger.LOCATION_ANOMALY,
    ])
    def test_intentionally_unmapped_triggers(self, trigger):
        assert mappings_for(trigger) == []

    def test_every_network_pattern_has_a_trigger(self):
        for p in NetworkPatternType:
            assert RegulatoryTrigger(p.value)

    def test_source_files_exist_in_repo_layout(self):
        for r in REFERENCES.values():
            assert r.source_file.startswith("dataset/raw/regulatory/")

    @pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext not installed")
    def test_excerpts_appear_verbatim_in_source_pdf(self):
        """Provenance: each excerpt must exist (whitespace-normalised) in its PDF."""
        cache: dict[str, str] = {}

        def norm(s: str) -> str:
            s = s.replace("’", "'")
            return re.sub(r"\s+", " ", s).strip()

        def strip_watermark(text: str) -> str:
            # The RBI PDF has a diagonal "Withdrawn" watermark whose letters
            # are interleaved as short trailing fragments on body lines.
            lines = [re.sub(r"\s{3,}(aw|n|ith|dr|W|ithdr)\s*$", "", ln) for ln in text.splitlines()]
            lines = [ln for ln in lines if ln.strip() not in {"aw", "n", "ith", "dr", "W", "ithdr"}]
            # Drop page-footer / running-header noise around page breaks.
            lines = [ln for ln in lines if not re.match(
                r"^\W*(\d+|\d{4}-\d{4}\s+\d+|\d+\s+\W*\d{4}-\d{4}|THE FATF RECOMMENDATIONS|"
                r"INTERNATIONAL STANDARDS ON COMBATING.*)\s*$", ln)]
            return "\n".join(lines)

        missing = []
        for r in REFERENCES.values():
            path = REPO / r.source_file
            if not path.is_file():
                pytest.skip(f"source PDF not present: {r.source_file}")
            if r.source_file not in cache:
                # -layout preserves reading order of enumerated items.
                txt = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True,
                                     text=True, check=True).stdout
                cache[r.source_file] = norm(strip_watermark(txt))
            if norm(r.excerpt) not in cache[r.source_file]:
                missing.append(r.reference_id)
        assert not missing, f"excerpts not found verbatim: {missing}"


# ---------------------------------------------------------------------------
# Signal extractors
# ---------------------------------------------------------------------------

class TestAnomalySignal:
    def test_missing_agent1_unavailable(self):
        assert not sg.extract_anomaly(None).available

    @pytest.mark.parametrize("st", [AgentStatus.FAILED, AgentStatus.VALIDATION_ERROR])
    def test_failed_agent1_unavailable(self, st):
        assert not sg.extract_anomaly(make_a1(None, None, st)).available

    def test_uses_combined_confidence(self):
        r = sg.extract_anomaly(make_a1(0.42, 0.9))
        assert r.value == pytest.approx(0.42)
        assert r.evidence_refs[0].source_agent == "AGENT_1"

    def test_falls_back_to_xgboost(self):
        r = sg.extract_anomaly(make_a1(None, 0.7, AgentStatus.PARTIAL))
        assert r.value == pytest.approx(0.7)
        assert r.warnings  # degraded status warned

    def test_no_scores_unavailable(self):
        assert not sg.extract_anomaly(make_a1(None, None, AgentStatus.PARTIAL)).available

    def test_compatibility_warning_flagged(self):
        r = sg.extract_anomaly(make_a1(0.2, 0.2, AgentStatus.COMPATIBILITY_WARNING))
        assert r.available and any("COMPATIBILITY_WARNING" in w for w in r.warnings)


class TestDeviceSignal:
    def test_registered_device_is_zero(self):
        assert sg.extract_new_device(make_tx(), make_a2()).value == 0.0

    def test_unregistered_device_is_one(self):
        assert sg.extract_new_device(make_tx(), make_a2(device_r=device(False))).value == 1.0

    def test_unknown_device_is_one(self):
        r = sg.extract_new_device(make_tx(), make_a2(device_r=device(status=EvidenceStatus.NOT_FOUND)))
        assert r.value == 1.0

    def test_transaction_flag_wins_over_registry(self):
        r = sg.extract_new_device(make_tx(is_new_device=True), make_a2())
        assert r.value == 1.0 and len(r.evidence_refs) == 2

    def test_provider_error_without_flag_unavailable(self):
        r = sg.extract_new_device(make_tx(), make_a2(device_r=device(status=EvidenceStatus.PROVIDER_ERROR)))
        assert not r.available

    def test_no_agent2_uses_transaction_flag(self):
        assert sg.extract_new_device(make_tx(is_new_device=False), None).value == 0.0


class TestBeneficiarySignal:
    cfg = Agent4Config()

    def test_established_beneficiary_zero(self):
        assert sg.extract_new_beneficiary(make_tx(), make_a2(), self.cfg).value == 0.0

    def test_previous_fraud_flag(self):
        r = sg.extract_new_beneficiary(make_tx(), make_a2(beneficiary_r=beneficiary(prev_fraud=True)), self.cfg)
        assert r.value == 1.0 and "previously flagged" in r.rationale

    def test_beneficiary_own_history_not_used(self):
        """A beneficiary with no history of its own is not, by itself, a new relationship."""
        r = sg.extract_new_beneficiary(make_tx(), make_a2(beneficiary_r=beneficiary(known_tx=0)), self.cfg)
        assert r.value == 0.0

    def test_young_account_partial(self):
        r = sg.extract_new_beneficiary(make_tx(), make_a2(beneficiary_r=beneficiary(age_days=5)), self.cfg)
        assert r.value == 0.5

    def test_receiver_not_in_known_beneficiaries(self):
        r = sg.extract_new_beneficiary(make_tx(), make_a2(core_r=core_banking(known=())), self.cfg)
        assert r.value == 1.0

    def test_transaction_flag(self):
        r = sg.extract_new_beneficiary(make_tx(is_new_beneficiary=True), None, self.cfg)
        assert r.value == 1.0

    def test_nothing_available(self):
        a2 = make_a2(beneficiary_r=None, core_r=None)
        assert not sg.extract_new_beneficiary(make_tx(), a2, self.cfg).available


class TestTimingSignal:
    cfg = Agent4Config()

    def test_daytime_zero(self):
        assert sg.extract_unusual_timing(make_tx(hour=11), self.cfg).value == 0.0

    def test_night_one(self):
        assert sg.extract_unusual_timing(make_tx(hour=2), self.cfg).value == 1.0

    def test_uses_local_offset_not_utc(self):
        # 20:30 UTC is 02:00 IST next day — but the tx is stored in UTC, so
        # the local hour of the stored timestamp (20) is what we judge.
        tx = make_tx(hour=20, tz=timezone.utc)
        assert sg.extract_unusual_timing(tx, self.cfg).value == 0.0
        tx_ist = make_tx(hour=2, tz=IST)
        assert sg.extract_unusual_timing(tx_ist, self.cfg).value == 1.0

    def test_recent_beneficiary(self):
        assert sg.extract_unusual_timing(make_tx(ben_added_min=10), self.cfg).value == 1.0

    def test_old_beneficiary(self):
        assert sg.extract_unusual_timing(make_tx(ben_added_min=600), self.cfg).value == 0.0

    def test_no_timestamp_unavailable(self):
        assert not sg.extract_unusual_timing(make_tx(hour=None), self.cfg).available


class TestNetworkSignal:
    cfg = Agent4Config()

    def test_missing(self):
        assert not sg.extract_network_risk(None, self.cfg).available

    @pytest.mark.parametrize("st", [Agent3Status.UNAVAILABLE, Agent3Status.FAILED,
                                    Agent3Status.VALIDATION_ERROR])
    def test_incomplete_status_not_clean(self, st):
        assert not sg.extract_network_risk(make_a3(st), self.cfg).available

    def test_complete_no_findings_zero(self):
        assert sg.extract_network_risk(make_a3(), self.cfg).value == 0.0

    def test_partial_no_findings_unavailable(self):
        assert not sg.extract_network_risk(make_a3(Agent3Status.PARTIAL), self.cfg).available

    def test_max_heuristic_score(self):
        a3 = make_a3(findings=[finding(score=0.3), finding(NetworkPatternType.LAYERING, 0.9)])
        r = sg.extract_network_risk(a3, self.cfg)
        assert r.value == pytest.approx(0.9) and len(r.evidence_refs) == 2

    def test_missing_heuristic_uses_default(self):
        r = sg.extract_network_risk(make_a3(findings=[finding(score=None)]), self.cfg)
        assert r.value == pytest.approx(0.5)

    def test_partial_with_findings_warns(self):
        r = sg.extract_network_risk(make_a3(Agent3Status.PARTIAL, [finding()]), self.cfg)
        assert r.available and r.warnings


class TestSanctionsSignal:
    def test_clean(self):
        s = sg.extract_sanctions(make_a2())
        assert s.result.value == 0.0 and not s.match_found and not s.screening_failed

    def test_account_match(self):
        s = sg.extract_sanctions(make_a2(acct=sanction(True)))
        assert s.result.value == 1.0 and s.match_found

    def test_both_failed(self):
        s = sg.extract_sanctions(make_a2(subj=None, acct=None))
        assert not s.result.available and s.screening_failed

    def test_one_failed_one_clean_is_flagged(self):
        s = sg.extract_sanctions(make_a2(subj=None))
        assert s.result.value == 0.0 and s.screening_failed

    def test_not_attempted_subject_is_not_failure(self):
        a2 = make_a2(subj=None, provider_status={"SANCTIONS_SUBJECT": EvidenceStatus.VALIDATION_ERROR})
        s = sg.extract_sanctions(a2)
        assert s.result.value == 0.0 and not s.screening_failed
        assert any("not attempted" in w for w in s.result.warnings)

    def test_error_response_object(self):
        s = sg.extract_sanctions(make_a2(acct=sanction(None, EvidenceStatus.AUTH_ERROR),
                                         subj=sanction(None, EvidenceStatus.PROVIDER_ERROR)))
        assert s.screening_failed and not s.result.available

    def test_match_with_other_failed_is_match(self):
        s = sg.extract_sanctions(make_a2(subj=None, acct=sanction(True)))
        assert s.match_found and not s.screening_failed

    def test_no_agent2(self):
        s = sg.extract_sanctions(None)
        assert s.screening_failed and not s.result.available


class TestLocationSignal:
    def test_anomalous(self):
        assert sg.extract_location(make_a2(geo_r=geo(True))).value == 1.0

    def test_normal(self):
        assert sg.extract_location(make_a2()).value == 0.0

    def test_undetermined(self):
        assert not sg.extract_location(make_a2(geo_r=geo(None))).available

    def test_missing(self):
        assert not sg.extract_location(make_a2(geo_r=None)).available


# ---------------------------------------------------------------------------
# End-to-end assessment
# ---------------------------------------------------------------------------

class TestAssessment:
    def test_clean_case(self):
        out = assess()
        assert out.status == Agent4Status.COMPLETE
        assert out.recommended_action == RecommendedAction.CLEAR
        assert out.confidence == ConfidenceLevel.HIGH
        assert out.evidence_coverage == pytest.approx(1.0)
        assert not out.sar_recommendation.recommended
        assert out.regulatory_matches == [] and out.unmapped_triggers == []
        assert len(out.score_breakdown) == 7

    def test_score_reproducible_from_breakdown(self):
        out = assess(a1=make_a1(0.6), a2=make_a2(geo_r=geo(True), device_r=device(False)))
        recomputed = 100 * sum(b.contribution for b in out.score_breakdown) / out.evidence_coverage
        assert out.risk_score == pytest.approx(recomputed, abs=0.01)
        expected = 100 * (0.30 * 0.6 + 0.10 + 0.10)
        assert out.risk_score == pytest.approx(expected, abs=0.01)

    def test_unavailable_signal_renormalised_not_zeroed(self):
        out = assess(a1=make_a1(0.8), a3=None)
        r = row(out, RiskSignal.NETWORK_RISK)
        assert not r.available and r.value is None and r.contribution == 0.0
        assert out.status == Agent4Status.PARTIAL
        assert out.evidence_coverage == pytest.approx(0.80)
        assert out.risk_score == pytest.approx(100 * 0.30 * 0.8 / 0.80, abs=0.01)
        assert RiskSignal.NETWORK_RISK in out.unavailable_signals

    def test_high_score_blocks(self):
        a2 = make_a2(device_r=device(False), beneficiary_r=beneficiary(prev_fraud=True), geo_r=geo(True))
        out = assess(tx=make_tx(hour=2), a1=make_a1(0.95),
                     a2=a2, a3=make_a3(findings=[finding(score=1.0)]))
        assert out.risk_score >= 75
        assert out.recommended_action == RecommendedAction.BLOCK
        assert out.sar_recommendation.recommended
        assert any(b.startswith("SCORE_BAND_BLOCK") for b in out.sar_recommendation.basis)

    def test_escalate_band_recommends_sar(self):
        a2 = make_a2(device_r=device(False), geo_r=geo(True))
        out = assess(a1=make_a1(0.9), a2=a2, a3=make_a3(findings=[finding(score=0.5)]))
        assert out.score_band_action == RecommendedAction.ESCALATE
        assert out.sar_recommendation.recommended

    def test_sanctions_match_forces_block_regardless_of_score(self):
        out = assess(a2=make_a2(acct=sanction(True)))
        assert out.score_band_action == RecommendedAction.CLEAR
        assert out.recommended_action == RecommendedAction.BLOCK
        assert [o.rule_id for o in out.overrides_applied] == ["OVR-SANCTIONS-MATCH"]
        assert out.sar_recommendation.basis == ["OVR-SANCTIONS-MATCH"]
        refs = {m.reference_id for m in out.regulatory_matches}
        assert {"FATF-R6", "FATF-R16-SANCTIONS", "FATF-R20"} <= refs

    def test_sanctions_override_can_be_disabled(self):
        cfg = Agent4Config(sanctions_match_forces_block=False)
        out = assess(a2=make_a2(acct=sanction(True)), cfg=cfg)
        assert out.recommended_action != RecommendedAction.BLOCK

    def test_sanctions_failure_forces_review(self):
        out = assess(a2=make_a2(subj=None, acct=None))
        assert out.recommended_action == RecommendedAction.HUMAN_REVIEW
        assert "OVR-SANCTIONS-UNAVAILABLE" in [o.rule_id for o in out.overrides_applied]
        assert not out.sar_recommendation.recommended

    def test_low_coverage_forces_review_and_low_confidence(self):
        out = assess(a1=None, a2=None, a3=None)
        # only UNUSUAL_TIMING (0.05) available from the transaction itself
        assert out.evidence_coverage == pytest.approx(0.05)
        assert out.recommended_action == RecommendedAction.HUMAN_REVIEW
        assert out.confidence == ConfidenceLevel.LOW
        assert "OVR-LOW-COVERAGE" in [o.rule_id for o in out.overrides_applied]

    def test_no_signal_at_all_fails_safe(self):
        out = assess(tx=make_tx(hour=None), a1=None, a2=None, a3=None)
        assert out.status == Agent4Status.FAILED
        assert out.risk_score is None
        assert out.recommended_action == RecommendedAction.HUMAN_REVIEW

    def test_override_never_lowers_action(self):
        a2 = make_a2(subj=None, acct=None, device_r=device(False), geo_r=geo(True),
                     beneficiary_r=beneficiary(prev_fraud=True))
        out = assess(tx=make_tx(hour=2), a1=make_a1(1.0), a2=a2,
                     a3=make_a3(findings=[finding(score=1.0)]))
        assert out.score_band_action == RecommendedAction.BLOCK
        assert out.recommended_action == RecommendedAction.BLOCK

    def test_degraded_upstream_gives_medium_confidence(self):
        out = assess(a1=make_a1(0.2, 0.2, AgentStatus.COMPATIBILITY_WARNING))
        assert out.confidence == ConfidenceLevel.MEDIUM
        assert any("Agent 1 status COMPATIBILITY_WARNING" in r for r in out.confidence_reasons)

    def test_mule_finding_maps_to_rbi_and_fatf(self):
        out = assess(a3=make_a3(findings=[finding(NetworkPatternType.MULE_LIKE)]))
        refs = {(m.trigger, m.reference_id) for m in out.regulatory_matches}
        assert (RegulatoryTrigger.MULE_LIKE, "RBI-FRM-3.4.2") in refs
        assert (RegulatoryTrigger.MULE_LIKE, "FATF-INR10-P20") in refs
        m = out.regulatory_matches[0]
        assert m.case_transaction_id == "T-001"
        assert m.verification_status == VerificationStatus.UNVERIFIED
        assert m.excerpt and m.source_file and m.pdf_page > 0

    def test_duplicate_patterns_mapped_once(self):
        out = assess(a3=make_a3(findings=[finding(), finding()]))
        mule = [m for m in out.regulatory_matches if m.trigger == RegulatoryTrigger.MULE_LIKE]
        assert len(mule) == len(mappings_for(RegulatoryTrigger.MULE_LIKE))

    def test_unmapped_triggers_reported_not_invented(self):
        a2 = make_a2(device_r=device(False), geo_r=geo(True))
        out = assess(tx=make_tx(hour=2), a2=a2)
        assert set(out.unmapped_triggers) == {
            RegulatoryTrigger.NEW_DEVICE, RegulatoryTrigger.LOCATION_ANOMALY,
            RegulatoryTrigger.UNUSUAL_TIMING}
        assert all(m.trigger not in out.unmapped_triggers for m in out.regulatory_matches)

    def test_unusual_transaction_trigger_from_anomaly(self):
        out = assess(a1=make_a1(0.7))
        assert RegulatoryTrigger.UNUSUAL_TRANSACTION in {m.trigger for m in out.regulatory_matches}

    def test_kyc_and_pep_triggers(self):
        out = assess(a2=make_a2(kyc_r=kyc("PENDING", pep=True)))
        trig = {m.trigger for m in out.regulatory_matches}
        assert {RegulatoryTrigger.KYC_NOT_VERIFIED, RegulatoryTrigger.PEP_INVOLVED} <= trig

    def test_provenance_refs_on_evidence_rows(self):
        out = assess(a2=make_a2(geo_r=geo(True)))
        ref = row(out, RiskSignal.LOCATION_ANOMALY).evidence_refs[0]
        assert ref.source_agent == "AGENT_2" and ref.source_mode == "MOCK"
        assert ref.reference_id and ref.retrieved_at

    def test_config_and_mapping_recorded(self):
        out = assess()
        assert out.config_version == "0.1.0-proposed"
        assert out.config_approval_status.startswith("PROPOSED")
        assert out.mapping_version
        assert out.config_snapshot["weights"]["NETWORK_RISK"] == 0.20

    def test_deterministic(self):
        a1, a2, a3 = make_a1(0.4), make_a2(device_r=device(False)), make_a3(findings=[finding()])
        o1, o2 = assess(a1=a1, a2=a2, a3=a3), assess(a1=a1, a2=a2, a3=a3)
        strip = lambda o: o.model_dump(exclude={"agent4_run_id", "assessed_at_utc"})  # noqa: E731
        assert strip(o1) == strip(o2)

    def test_output_is_frozen(self):
        out = assess()
        with pytest.raises(Exception):
            out.risk_score = 99.0  # type: ignore[misc]

    def test_upstream_linkage(self):
        a2, a3 = make_a2(), make_a3()
        out = assess(a2=a2, a3=a3)
        assert out.agent2_run_id == a2.agent2_run_id
        assert out.agent3_run_id == a3.agent3_run_id
        assert out.agent1_status == "COMPLETE"


class TestAgentInterface:
    def test_call_writes_only_agent4_output(self):
        tx, a1, a2, a3 = make_tx(), make_a1(), make_a2(), make_a3()
        state = {"transaction": tx, "agent1_output": a1, "agent2_output": a2,
                 "agent3_output": a3, "other": 1}
        new = RiskAssessorAgent()(state)
        assert isinstance(new["agent4_output"], Agent4Output)
        for k in state:
            assert new[k] is state[k]
        assert "agent4_output" not in state

    def test_call_falls_back_to_agent1_inside_agent2(self):
        a1 = make_a1(0.77)
        a2 = make_a2().model_copy(update={"agent1_output": a1})
        new = RiskAssessorAgent()({"transaction": make_tx(), "agent2_output": a2,
                                   "agent3_output": make_a3()})
        assert row(new["agent4_output"], RiskSignal.ANOMALY).value == pytest.approx(0.77)

    def test_missing_transaction_validation_error(self):
        out = RiskAssessorAgent()({})["agent4_output"]
        assert out.status == Agent4Status.VALIDATION_ERROR
        assert out.recommended_action == RecommendedAction.HUMAN_REVIEW
        assert out.risk_score is None

    def test_internal_error_fails_safe(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("secret detail")
        monkeypatch.setattr("src.agents.agent4.risk_assessor.extract_location", boom)
        out = assess()
        assert out.status == Agent4Status.FAILED
        assert out.recommended_action == RecommendedAction.HUMAN_REVIEW
        assert out.errors == ["Risk assessment failed: RuntimeError"]

    def test_pipeline_state_declares_agent4(self):
        from src.agents.sentinel_pipeline import SentinelState
        assert "agent4_output" in SentinelState.__annotations__
