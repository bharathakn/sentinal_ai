"""
Tests for src/ml/explainer.py

Verifies:
- global_importance returns a DataFrame with required columns
- explain_prediction returns required keys and disclaimer
- SHAP values are finite (no NaN/Inf)
- Explanation note clearly states it is not proof of fraud
- top_n limiting works correctly
"""

from __future__ import annotations

import numpy as np
import pytest

from ml.trainer import train
from ml.explainer import global_importance, explain_prediction


@pytest.fixture
def trained_model_and_data(small_ieee_cis_fixture, tmp_path):
    X, y = small_ieee_cis_fixture
    model_dir = tmp_path / "models/xgboost"
    results = train(X, y, model_dir=model_dir)
    return results


class TestGlobalImportance:
    def test_returns_dataframe_with_required_cols(self, trained_model_and_data):
        r = trained_model_and_data
        df = global_importance(r["model"], r["X_train_t"], r["feature_names"], max_display=10)
        assert "feature" in df.columns
        assert "mean_abs_shap" in df.columns

    def test_max_display_respected(self, trained_model_and_data):
        r = trained_model_and_data
        df = global_importance(r["model"], r["X_train_t"], r["feature_names"], max_display=5)
        assert len(df) <= 5

    def test_values_are_non_negative(self, trained_model_and_data):
        r = trained_model_and_data
        df = global_importance(r["model"], r["X_train_t"], r["feature_names"], max_display=10)
        assert (df["mean_abs_shap"] >= 0).all()

    def test_sorted_descending(self, trained_model_and_data):
        r = trained_model_and_data
        df = global_importance(r["model"], r["X_train_t"], r["feature_names"], max_display=10)
        vals = df["mean_abs_shap"].tolist()
        assert vals == sorted(vals, reverse=True)


class TestExplainPrediction:
    def test_returns_required_keys(self, trained_model_and_data):
        r = trained_model_and_data
        x_row = r["X_test_t"][0]
        result = explain_prediction(r["model"], x_row, r["feature_names"])
        required = {"base_value", "shap_sum", "top_contributors", "explanation_note"}
        assert required.issubset(result.keys())

    def test_top_n_limiting(self, trained_model_and_data):
        r = trained_model_and_data
        x_row = r["X_test_t"][0]
        result = explain_prediction(r["model"], x_row, r["feature_names"], top_n=3)
        assert len(result["top_contributors"]) <= 3

    def test_contributor_keys(self, trained_model_and_data):
        r = trained_model_and_data
        x_row = r["X_test_t"][0]
        result = explain_prediction(r["model"], x_row, r["feature_names"])
        for contrib in result["top_contributors"]:
            assert "feature" in contrib
            assert "shap_value" in contrib
            assert "direction" in contrib

    def test_direction_values_valid(self, trained_model_and_data):
        r = trained_model_and_data
        x_row = r["X_test_t"][0]
        result = explain_prediction(r["model"], x_row, r["feature_names"])
        valid_dirs = {"increases_fraud_score", "decreases_fraud_score"}
        for contrib in result["top_contributors"]:
            assert contrib["direction"] in valid_dirs

    def test_shap_values_are_finite(self, trained_model_and_data):
        r = trained_model_and_data
        x_row = r["X_test_t"][0]
        result = explain_prediction(r["model"], x_row, r["feature_names"])
        for contrib in result["top_contributors"]:
            assert np.isfinite(contrib["shap_value"])

    def test_explanation_note_disclaims_proof(self, trained_model_and_data):
        """The explanation note must NOT claim SHAP proves fraud."""
        r = trained_model_and_data
        x_row = r["X_test_t"][0]
        result = explain_prediction(r["model"], x_row, r["feature_names"])
        note = result["explanation_note"].lower()
        assert "model" in note
        assert any(word in note for word in ["behaviour", "behavior", "attribution"]), (
            "Explanation note should describe model behaviour, not make fraud claims"
        )
