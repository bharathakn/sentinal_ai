"""
Tests for src/ml/predictor.py

Verifies:
- FraudPredictor loads from saved artifacts
- predict_proba returns values in [0, 1]
- predict returns binary 0/1 with custom threshold
- predict_transaction returns expected keys and disclaimer
- Predictor works on unseen transactions (all-NaN fixture)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.trainer import train
from ml.predictor import FraudPredictor


@pytest.fixture
def trained_predictor(small_ieee_cis_fixture, tmp_path):
    """Train a model, save artifacts, return an initialised FraudPredictor."""
    X, y = small_ieee_cis_fixture
    model_dir = tmp_path / "models/xgboost"
    train(X, y, model_dir=model_dir)
    return FraudPredictor(model_dir=str(model_dir)), tmp_path


class TestFraudPredictorBasics:
    def test_predict_proba_range(self, trained_predictor, small_ieee_cis_fixture):
        predictor, _ = trained_predictor
        X, _ = small_ieee_cis_fixture
        probas = predictor.predict_proba(X.iloc[:20])
        assert probas.shape == (20,)
        assert (probas >= 0).all() and (probas <= 1).all()

    def test_predict_binary_output(self, trained_predictor, small_ieee_cis_fixture):
        predictor, _ = trained_predictor
        X, _ = small_ieee_cis_fixture
        preds = predictor.predict(X.iloc[:20])
        assert set(preds).issubset({0, 1})

    def test_custom_threshold(self, trained_predictor, small_ieee_cis_fixture):
        predictor, _ = trained_predictor
        X, _ = small_ieee_cis_fixture
        preds_low = predictor.predict(X.iloc[:50], threshold=0.1)
        preds_high = predictor.predict(X.iloc[:50], threshold=0.9)
        # Lower threshold → more positives
        assert preds_low.sum() >= preds_high.sum()

    def test_feature_names_accessible(self, trained_predictor):
        predictor, _ = trained_predictor
        assert isinstance(predictor.feature_names, list)
        assert len(predictor.feature_names) > 0

    def test_metadata_accessible(self, trained_predictor):
        predictor, _ = trained_predictor
        assert "model_version" in predictor.metadata
        assert "classification_threshold" in predictor.metadata


class TestPredictTransaction:
    def test_predict_transaction_returns_required_keys(self, trained_predictor):
        predictor, _ = trained_predictor
        result = predictor.predict_transaction({"TransactionAmt": 250.0, "ProductCD": "W"})
        required = {"fraud_probability", "is_fraud_predicted", "threshold_used", "model_version", "note"}
        assert required.issubset(result.keys())

    def test_predict_transaction_drops_leakage_columns(self, trained_predictor):
        predictor, _ = trained_predictor
        # Even if caller provides isFraud and TransactionID, no error should occur
        result = predictor.predict_transaction({
            "TransactionID": 9999,
            "isFraud": 1,  # leakage — must be stripped
            "TransactionAmt": 100.0,
        })
        assert "fraud_probability" in result

    def test_predict_transaction_probability_in_range(self, trained_predictor):
        predictor, _ = trained_predictor
        result = predictor.predict_transaction({"TransactionAmt": 9999.0})
        assert 0.0 <= result["fraud_probability"] <= 1.0

    def test_predict_transaction_note_is_disclaimer(self, trained_predictor):
        """The result must carry the model-not-proof-of-fraud disclaimer."""
        predictor, _ = trained_predictor
        result = predictor.predict_transaction({})
        note = result["note"]
        assert "not proof" in note.lower() or "statistical" in note.lower()

    def test_predict_transaction_on_empty_dict(self, trained_predictor):
        """All-NaN input must not crash the predictor."""
        predictor, _ = trained_predictor
        result = predictor.predict_transaction({})
        assert 0.0 <= result["fraud_probability"] <= 1.0

    def test_predictor_raises_on_missing_artifacts(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            FraudPredictor(model_dir=str(tmp_path / "no_models"))
