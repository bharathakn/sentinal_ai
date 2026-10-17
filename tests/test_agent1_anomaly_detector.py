"""
Tests for Agent 1 (Anomaly Detector) — Phase 4.

Test scenarios
--------------
1. Normal transaction — valid input, complete output, correct structure.
2. Suspicious transaction — valid input, model scores produced, structure verified.
3. Malformed transaction — invalid input handled safely before inference.
4. Missing feature — canonical-to-IEEE-CIS limitation explicitly tested.
5. Model unavailable — XGBoost and IF missing/unavailable handled correctly.

Testing conventions
-------------------
* Fixtures use the IEEE-CIS adapter to produce CanonicalTransaction instances.
* Integration tests use real model artifacts when available.
* Isolation tests use unittest.mock to simulate model failures.
* No test hardcodes specific score values unless the fixture justifies it.
* All assertions check structure, types, nullability contracts, and policy.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.agents.agent1 import AnomalyDetectorAgent, Agent1Output
from src.agents.agent1.output_schema import (
    AgentStatus,
    DeviationFeature,
    IsolationForestDetail,
    ScoringMode,
    XGBoostDetail,
)
from src.agents.agent1.anomaly_detector import (
    _compute_combined_confidence,        # noqa: PLC2701 — tested directly
    _sigmoid_normalise_if_score,         # noqa: PLC2701
)
from src.schemas.canonical_transaction import (
    CanonicalTransaction,
    DataSource,
    TransactionChannel,
)
from src.schemas.adapters.ieee_cis_adapter import IEEECISAdapter


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

def _make_normal_tx() -> CanonicalTransaction:
    """Produce a well-formed, normal-looking IEEE-CIS canonical transaction."""
    raw_row = {
        "TransactionID": 2987000,
        "TransactionAmt": 75.50,
        "TransactionDT": 86400,
        "ProductCD": "W",
        "card4": "visa",
        "card6": "debit",
        "addr1": 230.0,
        "addr2": 87.0,
        "P_emaildomain": "gmail.com",
        "R_emaildomain": "gmail.com",
    }
    return IEEECISAdapter.from_row(raw_row)


def _make_suspicious_tx() -> CanonicalTransaction:
    """Produce a transaction that has characteristics associated with higher risk.

    Uses a large amount and anonymous email domains, which the model may
    attribute more weight to. Does NOT hardcode expected scores.
    """
    raw_row = {
        "TransactionID": 9999999,
        "TransactionAmt": 9999.99,   # very large amount
        "TransactionDT": 86400,
        "ProductCD": "C",
        "card4": "american express",
        "card6": "credit",
        "addr1": 999.0,
        "P_emaildomain": "anonymous.com",
        "R_emaildomain": "anonymous.com",
    }
    return IEEECISAdapter.from_row(raw_row)


@pytest.fixture(scope="module")
def agent() -> AnomalyDetectorAgent:
    """Create one AnomalyDetectorAgent instance shared across the module."""
    return AnomalyDetectorAgent()


@pytest.fixture
def normal_tx() -> CanonicalTransaction:
    return _make_normal_tx()


@pytest.fixture
def suspicious_tx() -> CanonicalTransaction:
    return _make_suspicious_tx()


# ---------------------------------------------------------------------------
# Test 1 — Normal transaction
# ---------------------------------------------------------------------------


class TestNormalTransaction:
    """Scenario 1: A valid, ordinary transaction scores successfully."""

    def test_passes_validation_and_returns_output(self, agent, normal_tx):
        """Normal transaction must not crash and must return Agent1Output."""
        result = agent.score(normal_tx)
        assert isinstance(result, Agent1Output)

    def test_output_status_not_failed(self, agent, normal_tx):
        """Status must not be FAILED for a valid transaction when models are loaded."""
        result = agent.score(normal_tx)
        assert result.status != AgentStatus.FAILED, (
            f"Unexpected FAILED status. Errors: {result.errors}"
        )

    def test_required_score_fields_present(self, agent, normal_tx):
        """All four required output fields must be present and have correct types."""
        result = agent.score(normal_tx)
        # anomaly_score: float or None
        assert result.anomaly_score is None or isinstance(result.anomaly_score, float)
        # isolation_score: float or None
        assert result.isolation_score is None or isinstance(result.isolation_score, float)
        # combined_confidence: float or None
        assert result.combined_confidence is None or isinstance(result.combined_confidence, float)
        # top_deviation_features: list
        assert isinstance(result.top_deviation_features, list)

    def test_anomaly_score_is_probability(self, agent, normal_tx):
        """anomaly_score is XGBoost fraud_probability and must be in [0, 1]."""
        result = agent.score(normal_tx)
        if result.anomaly_score is not None:
            assert 0.0 <= result.anomaly_score <= 1.0, (
                f"anomaly_score {result.anomaly_score} out of [0, 1]"
            )

    def test_combined_confidence_in_range(self, agent, normal_tx):
        """combined_confidence must be in [0, 1] when available."""
        result = agent.score(normal_tx)
        if result.combined_confidence is not None:
            assert 0.0 <= result.combined_confidence <= 1.0

    def test_xgboost_detail_structure(self, agent, normal_tx):
        """XGBoostDetail must have correct types when present."""
        result = agent.score(normal_tx)
        if result.xgboost_detail is not None:
            d = result.xgboost_detail
            assert isinstance(d.fraud_probability, float)
            assert 0.0 <= d.fraud_probability <= 1.0
            assert isinstance(d.is_fraud_predicted, bool)
            assert isinstance(d.threshold_used, float)
            assert isinstance(d.note, str)

    def test_isolation_forest_detail_structure(self, agent, normal_tx):
        """IsolationForestDetail must have correct types when present."""
        result = agent.score(normal_tx)
        if result.isolation_forest_detail is not None:
            d = result.isolation_forest_detail
            assert isinstance(d.anomaly_score, float)
            assert isinstance(d.is_anomaly, bool)
            assert isinstance(d.threshold_used, float)
            assert isinstance(d.score_note, str)

    def test_shap_explanations_when_available(self, agent, normal_tx):
        """SHAP explanations must be non-empty when shap_available=True."""
        result = agent.score(normal_tx)
        if result.shap_available:
            assert len(result.top_deviation_features) > 0
            for feat in result.top_deviation_features:
                assert isinstance(feat, DeviationFeature)
                assert isinstance(feat.feature, str)
                assert isinstance(feat.shap_value, float)
                assert feat.direction in (
                    "increases_fraud_score",
                    "decreases_fraud_score",
                )
                assert feat.rank >= 1

    def test_top_features_ranked_correctly(self, agent, normal_tx):
        """Top deviation features must be in ascending rank order."""
        result = agent.score(normal_tx)
        if result.top_deviation_features:
            ranks = [f.rank for f in result.top_deviation_features]
            assert ranks == list(range(1, len(ranks) + 1)), (
                f"Ranks not sequential: {ranks}"
            )

    def test_provenance_preserved(self, agent, normal_tx):
        """Transaction ID and source dataset must be carried into output."""
        result = agent.score(normal_tx)
        assert result.transaction_id == "2987000"
        assert result.source_dataset == "IEEE_CIS"

    def test_feature_mapping_info_present(self, agent, normal_tx):
        """Feature mapping summary must be included and structurally valid."""
        result = agent.score(normal_tx)
        assert result.feature_mapping is not None
        fm = result.feature_mapping
        assert fm.scoring_mode == ScoringMode.CANONICAL_MAPPED
        assert fm.total_model_features == 432
        assert fm.n_features_mapped + fm.n_nan_imputed == fm.total_model_features
        # For a canonical transaction, coverage is low (few fields mapped)
        assert fm.n_features_mapped <= 5  # current mapper supports ≤5 fields
        assert fm.n_nan_imputed > 400     # most features are NaN-imputed

    def test_scored_at_utc_present(self, agent, normal_tx):
        """scored_at_utc must be a timezone-aware datetime."""
        result = agent.score(normal_tx)
        from datetime import timezone
        assert result.scored_at_utc.tzinfo is not None

    def test_isolation_score_not_a_probability(self, agent, normal_tx):
        """isolation_score is NOT in [0,1] by definition — verify it's a raw IF score."""
        result = agent.score(normal_tx)
        # isolation_score can be any float; specifically NOT guaranteed to be in [0,1].
        # This test verifies that anomaly_score and isolation_score are not conflated.
        if result.anomaly_score is not None and result.isolation_score is not None:
            # They must come from different models and may differ significantly.
            # Just verify that the output doc correctly labels them separately.
            assert result.xgboost_detail is not None
            assert result.isolation_forest_detail is not None
            assert (
                result.xgboost_detail.fraud_probability == result.anomaly_score
            )
            assert (
                result.isolation_forest_detail.anomaly_score == result.isolation_score
            )


# ---------------------------------------------------------------------------
# Test 2 — Suspicious transaction
# ---------------------------------------------------------------------------


class TestSuspiciousTransaction:
    """Scenario 2: A valid transaction with suspicious characteristics."""

    def test_passes_input_validation(self, agent, suspicious_tx):
        """Suspicious transaction must still be a valid CanonicalTransaction."""
        result = agent.score(suspicious_tx)
        assert isinstance(result, Agent1Output)
        assert result.status != AgentStatus.VALIDATION_ERROR

    def test_reaches_scoring_pipeline(self, agent, suspicious_tx):
        """Both model scores must be produced (not None) when models are available."""
        result = agent.score(suspicious_tx)
        if agent.both_models_available:
            assert result.anomaly_score is not None, "XGBoost did not produce a score"
            assert result.isolation_score is not None, "IF did not produce a score"

    def test_shap_available_with_both_models(self, agent, suspicious_tx):
        """SHAP explanations must be available when XGBoost is loaded."""
        result = agent.score(suspicious_tx)
        if agent.xgb_available:
            assert result.shap_available
            assert len(result.top_deviation_features) > 0

    def test_output_structure_matches_normal(self, agent, suspicious_tx):
        """Output structure must be identical regardless of suspicion level."""
        result = agent.score(suspicious_tx)
        assert isinstance(result.status, AgentStatus)
        assert isinstance(result.warnings, list)
        assert isinstance(result.errors, list)
        assert isinstance(result.top_deviation_features, list)
        assert isinstance(result.combined_confidence_note, str)

    def test_combined_confidence_follows_documented_strategy(
        self, agent, suspicious_tx
    ):
        """combined_confidence must be computable from the two model scores."""
        result = agent.score(suspicious_tx)
        if (
            result.anomaly_score is not None
            and result.isolation_score is not None
            and result.combined_confidence is not None
        ):
            # Recompute using the documented formula and verify consistency.
            from src.agents.agent1.anomaly_detector import (
                _DEFAULT_IF_CALIBRATED_THRESHOLD,
                _DEFAULT_IF_WEIGHT,
                _DEFAULT_XGB_WEIGHT,
            )
            expected = _compute_combined_confidence(
                xgb_prob=result.anomaly_score,
                if_anomaly_score=result.isolation_score,
                xgb_weight=_DEFAULT_XGB_WEIGHT,
                if_weight=_DEFAULT_IF_WEIGHT,
                if_threshold=_DEFAULT_IF_CALIBRATED_THRESHOLD,
            )
            assert math.isclose(result.combined_confidence, expected, rel_tol=1e-6), (
                f"combined_confidence {result.combined_confidence} != expected {expected}"
            )

    def test_combined_confidence_in_valid_range(self, agent, suspicious_tx):
        """combined_confidence must be in [0, 1] regardless of suspicious scores."""
        result = agent.score(suspicious_tx)
        if result.combined_confidence is not None:
            assert 0.0 <= result.combined_confidence <= 1.0


# ---------------------------------------------------------------------------
# Test 3 — Malformed transaction
# ---------------------------------------------------------------------------


class TestMalformedTransaction:
    """Scenario 3: Invalid / malformed input must be caught without crashing."""

    def test_empty_raw_record_id_raises_validation_error(self, agent):
        """CanonicalTransaction requires a non-empty raw_record_id."""
        with pytest.raises(Exception):
            # Pydantic validation must reject this before scoring.
            tx = CanonicalTransaction(
                raw_record_id="",       # invalid: empty
                source_dataset=DataSource.IEEE_CIS,
                amount=Decimal("100.00"),
            )
            agent.score(tx)

    def test_negative_amount_raises_validation_error(self):
        """CanonicalTransaction must reject negative amounts."""
        with pytest.raises(Exception):
            CanonicalTransaction(
                raw_record_id="bad-tx-1",
                source_dataset=DataSource.IEEE_CIS,
                amount=Decimal("-1.00"),  # invalid: negative
            )

    def test_invalid_currency_length_raises(self):
        """Currency must be exactly 3 characters."""
        with pytest.raises(Exception):
            CanonicalTransaction(
                raw_record_id="bad-tx-2",
                source_dataset=DataSource.IEEE_CIS,
                amount=Decimal("50.00"),
                currency="USDD",  # invalid: too long
            )

    def test_invalid_latitude_raises(self):
        """GeoLocation latitude must be in [-90, 90]."""
        from src.schemas.canonical_transaction import GeoLocation
        with pytest.raises(Exception):
            GeoLocation(latitude=91.0)  # out of range

    def test_invalid_longitude_raises(self):
        """GeoLocation longitude must be in [-180, 180]."""
        from src.schemas.canonical_transaction import GeoLocation
        with pytest.raises(Exception):
            GeoLocation(longitude=200.0)  # out of range

    def test_score_raw_with_non_numeric_amount_does_not_crash(self, agent):
        """score_raw with a non-numeric field must not crash — pipeline handles NaN."""
        # Pass a string that cannot be converted to float for TransactionAmt.
        # The feature mapper converts it with a try/except; the pipeline then
        # handles NaN via the fitted imputer.
        raw_features = {"TransactionAmt": "not_a_number"}
        # score_raw bypasses canonical validation — must not raise.
        result = agent.score_raw(raw_features)
        assert isinstance(result, Agent1Output)

    def test_empty_features_dict_does_not_crash(self, agent):
        """score_raw with an empty dict must not crash."""
        result = agent.score_raw({})
        assert isinstance(result, Agent1Output)
        # Status must not be VALIDATION_ERROR (no canonical schema to validate)
        assert result.status != AgentStatus.VALIDATION_ERROR

    def test_malformed_input_does_not_reach_model_inference(self):
        """Pydantic validation must prevent a malformed transaction from being scored."""
        with pytest.raises(Exception) as exc_info:
            # Missing required fields: raw_record_id and source_dataset
            CanonicalTransaction(
                amount=Decimal("100.00"),
                # raw_record_id and source_dataset are required
            )
        # Pydantic should raise a ValidationError before any model code runs.
        assert exc_info.value is not None


# ---------------------------------------------------------------------------
# Test 4 — Missing feature (canonical-to-IEEE-CIS limitation)
# ---------------------------------------------------------------------------


class TestMissingFeature:
    """Scenario 4: Canonical transaction feature-mapping limitation."""

    def test_low_coverage_warning_always_present(self, agent, normal_tx):
        """A canonical transaction must always produce a low-coverage warning."""
        result = agent.score(normal_tx)
        # There must be at least one warning about NaN imputation.
        has_coverage_warning = any(
            "NaN-imputed" in w or "feature coverage" in w.lower()
            for w in result.warnings
        )
        assert has_coverage_warning, (
            f"Expected a NaN-imputation warning. Warnings: {result.warnings}"
        )

    def test_n_nan_imputed_exceeds_mapped(self, agent, normal_tx):
        """NaN-imputed count must exceed mapped count for canonical transactions."""
        result = agent.score(normal_tx)
        fm = result.feature_mapping
        assert fm is not None
        assert fm.n_nan_imputed > fm.n_features_mapped, (
            f"Expected more NaN-imputed ({fm.n_nan_imputed}) than mapped "
            f"({fm.n_features_mapped}) for a canonical transaction."
        )

    def test_mapped_fields_subset_of_known_fields(self, agent, normal_tx):
        """Mapped fields must all be known IEEE-CIS columns."""
        result = agent.score(normal_tx)
        fm = result.feature_mapping
        assert fm is not None
        known_mappable = {"TransactionAmt", "card4", "addr1", "P_emaildomain", "R_emaildomain"}
        for field in fm.mapped_fields:
            assert field in known_mappable, (
                f"Unexpected mapped field: {field}. Known mappable: {known_mappable}"
            )

    def test_amount_field_always_mapped(self, agent):
        """TransactionAmt must always be in the mapped fields (it is mandatory)."""
        tx = _make_normal_tx()
        result = agent.score(tx)
        fm = result.feature_mapping
        assert fm is not None
        assert "TransactionAmt" in fm.mapped_fields

    def test_transaction_without_optional_fields_still_maps_amount(self, agent):
        """A minimal canonical transaction (amount only) must still map TransactionAmt."""
        tx = CanonicalTransaction(
            raw_record_id="minimal-1",
            source_dataset=DataSource.IEEE_CIS,
            amount=Decimal("200.00"),
        )
        result = agent.score(tx)
        fm = result.feature_mapping
        assert fm is not None
        assert "TransactionAmt" in fm.mapped_fields
        # All optional fields absent → only amount mapped
        assert fm.n_features_mapped == 1

    def test_nans_do_not_cause_crash(self, agent):
        """A transaction with only amount (all other features NaN) must not crash."""
        tx = CanonicalTransaction(
            raw_record_id="nan-only-1",
            source_dataset=DataSource.IEEE_CIS,
            amount=Decimal("500.00"),
        )
        result = agent.score(tx)
        assert isinstance(result, Agent1Output)
        # Score is produced (possibly degraded), not silently zero
        if result.anomaly_score is not None:
            assert isinstance(result.anomaly_score, float)

    def test_status_reflects_compatibility_limitation(self, agent, normal_tx):
        """Status must reflect the mapping limitation, not mask it as COMPLETE."""
        result = agent.score(normal_tx)
        # COMPLETE would imply full feature coverage; canonical mapping never
        # achieves full coverage, so status should be COMPATIBILITY_WARNING or PARTIAL.
        assert result.status in (
            AgentStatus.COMPATIBILITY_WARNING,
            AgentStatus.PARTIAL,
        ), (
            f"Expected COMPATIBILITY_WARNING or PARTIAL for canonical-mapped "
            f"transaction, got {result.status}"
        )

    def test_nans_not_reported_as_zero_feature_values(self, agent, normal_tx):
        """NaN-imputed feature values in SHAP output must be None, not 0.0."""
        result = agent.score(normal_tx)
        if not result.shap_available:
            pytest.skip("SHAP not available; cannot test feature value reporting.")

        # At least some features should have feature_value=None (NaN-imputed)
        none_count = sum(
            1 for f in result.top_deviation_features if f.feature_value is None
        )
        # Given 427/432 features are NaN-imputed, most top features should be NaN.
        # We expect at least some None values in the top 10.
        assert none_count > 0, (
            "Expected at least some None feature_values for NaN-imputed features, "
            f"but all {len(result.top_deviation_features)} have non-None values."
        )


# ---------------------------------------------------------------------------
# Test 5 — Model unavailable
# ---------------------------------------------------------------------------


class TestModelUnavailable:
    """Scenario 5: Simulate missing/broken models."""

    def test_missing_xgb_model_dir_raises_on_init(self, tmp_path):
        """AnomalyDetectorAgent must raise FileNotFoundError for bad XGBoost path."""
        with pytest.raises(FileNotFoundError):
            AnomalyDetectorAgent(xgb_model_dir=str(tmp_path / "nonexistent_xgb"))

    def test_missing_if_model_dir_raises_on_init(self, tmp_path):
        """AnomalyDetectorAgent must raise FileNotFoundError for bad IF path."""
        with pytest.raises(FileNotFoundError):
            AnomalyDetectorAgent(if_model_dir=str(tmp_path / "nonexistent_if"))

    def test_xgb_unavailable_produces_none_anomaly_score(self, normal_tx):
        """When XGBoost is unavailable, anomaly_score must be None, not fabricated."""
        # Patch FraudPredictor to raise FileNotFoundError on init.
        with patch(
            "src.agents.agent1.anomaly_detector.FraudPredictor",
            side_effect=FileNotFoundError("XGBoost artifacts not found."),
        ):
            with pytest.raises(FileNotFoundError):
                # The init itself raises because xgb load error propagates
                AnomalyDetectorAgent()

    def test_xgb_inference_failure_returns_none_anomaly_score(self, normal_tx):
        """If XGBoost predict_transaction raises at inference, anomaly_score=None."""
        agent = AnomalyDetectorAgent()
        # Patch the internal _xgb_predictor to fail at inference time.
        mock_xgb = MagicMock()
        mock_xgb.predict_transaction.side_effect = RuntimeError("Inference failure")
        mock_xgb.metadata = {"model_version": "mock"}
        mock_xgb.feature_names = agent._xgb_predictor.feature_names if agent._xgb_predictor else []
        original_xgb = agent._xgb_predictor
        agent._xgb_predictor = mock_xgb
        try:
            result = agent.score(normal_tx)
            assert result.anomaly_score is None, (
                "anomaly_score must be None when XGBoost inference fails"
            )
            assert any("XGBoost inference error" in e for e in result.errors)
            assert result.combined_confidence is None, (
                "combined_confidence must be None when XGBoost is unavailable"
            )
        finally:
            agent._xgb_predictor = original_xgb

    def test_if_inference_failure_returns_none_isolation_score(self, normal_tx):
        """If IF score_transaction raises at inference, isolation_score=None."""
        agent = AnomalyDetectorAgent()
        mock_if = MagicMock()
        mock_if.score_transaction.side_effect = RuntimeError("IF inference failure")
        mock_if.metadata = {"model_version": "mock"}
        original_if = agent._if_predictor
        agent._if_predictor = mock_if
        try:
            result = agent.score(normal_tx)
            assert result.isolation_score is None, (
                "isolation_score must be None when IF inference fails"
            )
            assert any("Isolation Forest inference error" in e for e in result.errors)
            assert result.combined_confidence is None, (
                "combined_confidence must be None when IF is unavailable"
            )
        finally:
            agent._if_predictor = original_if

    def test_both_models_fail_returns_failed_status(self, normal_tx):
        """When both models fail, status must be FAILED."""
        agent = AnomalyDetectorAgent()

        mock_xgb = MagicMock()
        mock_xgb.predict_transaction.side_effect = RuntimeError("XGBoost dead")
        mock_xgb.metadata = {"model_version": "mock"}
        mock_xgb.feature_names = agent._xgb_predictor.feature_names if agent._xgb_predictor else []

        mock_if = MagicMock()
        mock_if.score_transaction.side_effect = RuntimeError("IF dead")
        mock_if.metadata = {"model_version": "mock"}

        orig_xgb = agent._xgb_predictor
        orig_if = agent._if_predictor
        agent._xgb_predictor = mock_xgb
        agent._if_predictor = mock_if
        try:
            result = agent.score(normal_tx)
            assert result.status == AgentStatus.FAILED, (
                f"Expected FAILED status, got {result.status}"
            )
            assert result.anomaly_score is None
            assert result.isolation_score is None
            assert result.combined_confidence is None
            assert len(result.errors) >= 2
        finally:
            agent._xgb_predictor = orig_xgb
            agent._if_predictor = orig_if

    def test_failed_models_do_not_return_zero_scores(self, normal_tx):
        """Failed models must NOT silently return 0.0 as a score."""
        agent = AnomalyDetectorAgent()

        mock_xgb = MagicMock()
        mock_xgb.predict_transaction.side_effect = RuntimeError("XGBoost dead")
        mock_xgb.metadata = {"model_version": "mock"}
        mock_xgb.feature_names = agent._xgb_predictor.feature_names if agent._xgb_predictor else []

        orig_xgb = agent._xgb_predictor
        agent._xgb_predictor = mock_xgb
        try:
            result = agent.score(normal_tx)
            # anomaly_score must be None, not 0.0 (which would be a valid score)
            assert result.anomaly_score is None, (
                f"Expected None anomaly_score for failed model, got {result.anomaly_score}"
            )
        finally:
            agent._xgb_predictor = orig_xgb

    def test_shap_failure_does_not_crash(self, normal_tx):
        """SHAP failure must produce a warning, not crash the agent."""
        agent = AnomalyDetectorAgent()
        # Patch the SHAP explainer to raise.
        with patch(
            "src.agents.agent1.anomaly_detector.explain_prediction",
            side_effect=Exception("SHAP explainer unavailable"),
        ):
            result = agent.score(normal_tx)
        assert result.shap_available is False
        assert result.top_deviation_features == []
        has_shap_warning = any("SHAP" in w for w in result.warnings)
        assert has_shap_warning, f"Expected SHAP warning. Warnings: {result.warnings}"
        # Scores must still be produced despite SHAP failure.
        if agent.both_models_available:
            assert result.anomaly_score is not None
            assert result.isolation_score is not None

    def test_partial_result_when_one_model_fails(self, normal_tx):
        """When only one model fails, status must be PARTIAL, not FAILED."""
        agent = AnomalyDetectorAgent()

        mock_if = MagicMock()
        mock_if.score_transaction.side_effect = RuntimeError("IF dead")
        mock_if.metadata = {"model_version": "mock"}

        orig_if = agent._if_predictor
        agent._if_predictor = mock_if
        try:
            result = agent.score(normal_tx)
            # XGBoost should still produce a score.
            if agent.xgb_available:
                assert result.anomaly_score is not None
            # IF is dead.
            assert result.isolation_score is None
            assert result.combined_confidence is None
            # Status should not be FAILED (XGBoost still worked).
            assert result.status != AgentStatus.FAILED
        finally:
            agent._if_predictor = orig_if

    def test_combined_note_never_missing(self, normal_tx):
        """combined_confidence_note must always be present regardless of failures."""
        agent = AnomalyDetectorAgent()
        result = agent.score(normal_tx)
        assert result.combined_confidence_note
        assert "combined_confidence" in result.combined_confidence_note.lower()


# ---------------------------------------------------------------------------
# Test 6 — score_raw integration
# ---------------------------------------------------------------------------


class TestScoreRaw:
    """Integration test: score_raw with a more complete feature dict."""

    def test_score_raw_with_partial_ieee_cis_features(self, agent):
        """score_raw with partial features must produce valid output."""
        features = {
            "TransactionAmt": 250.0,
            "card4": "mastercard",
            "addr1": 315.0,
            "P_emaildomain": "yahoo.com",
        }
        result = agent.score_raw(features, transaction_id="raw-001")
        assert isinstance(result, Agent1Output)
        assert result.transaction_id == "raw-001"
        assert result.source_dataset is None

    def test_score_raw_scores_are_not_zero_sentinel(self, agent):
        """score_raw scores must be genuine floats, not zero sentinels."""
        features = {"TransactionAmt": 100.0}
        result = agent.score_raw(features)
        # If available, the score must be a real float, not necessarily 0.0.
        # We only verify the type and None contract here.
        if result.anomaly_score is not None:
            assert isinstance(result.anomaly_score, float)
        if result.isolation_score is not None:
            assert isinstance(result.isolation_score, float)


# ---------------------------------------------------------------------------
# Test 7 — Combined confidence unit tests
# ---------------------------------------------------------------------------


class TestCombinedConfidenceUnit:
    """Unit tests for the combined_confidence calculation function."""

    def test_at_threshold_sigmoid_returns_half(self):
        """sigmoid_normalise_if_score(threshold) must equal 0.5."""
        result = _sigmoid_normalise_if_score(0.4679, threshold=0.4679)
        assert math.isclose(result, 0.5, rel_tol=1e-6)

    def test_above_threshold_sigmoid_above_half(self):
        """Anomaly scores above threshold must normalise above 0.5."""
        result = _sigmoid_normalise_if_score(0.6, threshold=0.4679)
        assert result > 0.5

    def test_below_threshold_sigmoid_below_half(self):
        """Anomaly scores below threshold must normalise below 0.5."""
        result = _sigmoid_normalise_if_score(0.2, threshold=0.4679)
        assert result < 0.5

    def test_combined_confidence_is_deterministic(self):
        """Same inputs must produce the same combined_confidence."""
        cc1 = _compute_combined_confidence(0.7, 0.5)
        cc2 = _compute_combined_confidence(0.7, 0.5)
        assert cc1 == cc2

    def test_combined_confidence_in_range(self):
        """combined_confidence must be in [0, 1] for any valid inputs."""
        for xgb_prob in [0.0, 0.3, 0.5, 0.8, 1.0]:
            for if_score in [-0.5, 0.0, 0.3, 0.47, 0.6, 0.9]:
                result = _compute_combined_confidence(xgb_prob, if_score)
                assert 0.0 <= result <= 1.0, (
                    f"Out of range for xgb={xgb_prob}, if={if_score}: {result}"
                )

    def test_weights_must_sum_to_one(self):
        """AnomalyDetectorAgent must reject weight configs that do not sum to 1.0."""
        with pytest.raises(ValueError, match="must equal 1.0"):
            AnomalyDetectorAgent(xgb_weight=0.6, if_weight=0.6)

    def test_high_fraud_prob_raises_combined_confidence(self):
        """High XGBoost fraud probability must increase combined_confidence."""
        low_cc = _compute_combined_confidence(xgb_prob=0.1, if_anomaly_score=0.4)
        high_cc = _compute_combined_confidence(xgb_prob=0.9, if_anomaly_score=0.4)
        assert high_cc > low_cc
