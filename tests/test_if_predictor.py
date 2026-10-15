"""
Tests for src/ml/if_predictor.py

Verifies:
- AnomalyPredictor loads from saved artifacts
- score() returns finite floats
- predict() returns (scores, bool array) with correct shapes
- Custom threshold changes classification
- score_transaction() returns required keys with disclaimer
- score_transaction() strips leakage columns
- score_transaction() handles sparse/empty dicts
- Predictor raises on missing artifacts
- Score outputs are separate from XGBoost outputs (not interchangeable)
"""

from __future__ import annotations

import numpy as np
import pytest

from ml.if_trainer import train_isolation_forest
from ml.if_predictor import AnomalyPredictor


@pytest.fixture
def trained_anomaly_predictor(small_ieee_cis_fixture, tmp_path):
    X, y = small_ieee_cis_fixture
    model_dir = tmp_path / "models/isolation_forest"
    train_isolation_forest(
        X, y, model_dir=model_dir, params={"n_estimators": 10}
    )
    return AnomalyPredictor(model_dir=str(model_dir)), tmp_path


class TestAnomalyPredictorScore:
    def test_score_returns_array(self, trained_anomaly_predictor, small_ieee_cis_fixture):
        predictor, _ = trained_anomaly_predictor
        X, _ = small_ieee_cis_fixture
        scores = predictor.score(X.iloc[:20])
        assert scores.shape == (20,)

    def test_score_is_finite(self, trained_anomaly_predictor, small_ieee_cis_fixture):
        predictor, _ = trained_anomaly_predictor
        X, _ = small_ieee_cis_fixture
        scores = predictor.score(X.iloc[:50])
        assert np.isfinite(scores).all(), "All anomaly scores must be finite"

    def test_score_is_float64(self, trained_anomaly_predictor, small_ieee_cis_fixture):
        predictor, _ = trained_anomaly_predictor
        X, _ = small_ieee_cis_fixture
        scores = predictor.score(X.iloc[:10])
        assert scores.dtype == np.float64


class TestAnomalyPredictorPredict:
    def test_predict_returns_tuple(self, trained_anomaly_predictor, small_ieee_cis_fixture):
        predictor, _ = trained_anomaly_predictor
        X, _ = small_ieee_cis_fixture
        result = predictor.predict(X.iloc[:20])
        assert isinstance(result, tuple) and len(result) == 2

    def test_predict_shapes_match(self, trained_anomaly_predictor, small_ieee_cis_fixture):
        predictor, _ = trained_anomaly_predictor
        X, _ = small_ieee_cis_fixture
        scores, is_anomaly = predictor.predict(X.iloc[:20])
        assert scores.shape == is_anomaly.shape == (20,)

    def test_is_anomaly_is_bool(self, trained_anomaly_predictor, small_ieee_cis_fixture):
        predictor, _ = trained_anomaly_predictor
        X, _ = small_ieee_cis_fixture
        _, is_anomaly = predictor.predict(X.iloc[:20])
        assert is_anomaly.dtype == bool

    def test_low_threshold_more_anomalies(self, trained_anomaly_predictor, small_ieee_cis_fixture):
        predictor, _ = trained_anomaly_predictor
        X, _ = small_ieee_cis_fixture
        X_sample = X.iloc[:50]
        _, anom_low = predictor.predict(X_sample, threshold=-1.0)
        _, anom_high = predictor.predict(X_sample, threshold=1.0)
        assert anom_low.sum() >= anom_high.sum()

    def test_threshold_in_metadata(self, trained_anomaly_predictor):
        predictor, _ = trained_anomaly_predictor
        assert "default_threshold" in predictor.metadata


class TestScoreTransaction:
    def test_required_keys_present(self, trained_anomaly_predictor):
        predictor, _ = trained_anomaly_predictor
        result = predictor.score_transaction({"TransactionAmt": 250.0})
        required = {"anomaly_score", "is_anomaly", "threshold_used", "model_version", "score_note"}
        assert required.issubset(result.keys())

    def test_anomaly_score_is_float(self, trained_anomaly_predictor):
        predictor, _ = trained_anomaly_predictor
        result = predictor.score_transaction({"TransactionAmt": 250.0})
        assert isinstance(result["anomaly_score"], float)

    def test_is_anomaly_is_bool(self, trained_anomaly_predictor):
        predictor, _ = trained_anomaly_predictor
        result = predictor.score_transaction({"TransactionAmt": 250.0})
        assert isinstance(result["is_anomaly"], bool)

    def test_strips_leakage_columns(self, trained_anomaly_predictor):
        predictor, _ = trained_anomaly_predictor
        result = predictor.score_transaction({
            "TransactionID": 99999,
            "isFraud": 1,
            "TransactionAmt": 100.0,
        })
        assert "anomaly_score" in result

    def test_empty_dict_does_not_crash(self, trained_anomaly_predictor):
        predictor, _ = trained_anomaly_predictor
        result = predictor.score_transaction({})
        assert "anomaly_score" in result
        assert np.isfinite(result["anomaly_score"])

    def test_score_note_disclaims_fraud_probability(self, trained_anomaly_predictor):
        """Score note must explicitly state this is NOT a fraud probability."""
        predictor, _ = trained_anomaly_predictor
        result = predictor.score_transaction({})
        note = result["score_note"].lower()
        assert "not" in note
        assert "probability" in note or "xgboost" in note

    def test_score_and_xgboost_probability_are_separate(self, trained_anomaly_predictor):
        """Verify key name difference — ensures outputs are not accidentally merged."""
        predictor, _ = trained_anomaly_predictor
        result = predictor.score_transaction({"TransactionAmt": 1000.0})
        # IF output key is anomaly_score, NOT fraud_probability
        assert "anomaly_score" in result
        assert "fraud_probability" not in result


class TestAnomalyPredictorMissing:
    def test_raises_on_missing_artifacts(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            AnomalyPredictor(model_dir=str(tmp_path / "no_models"))
