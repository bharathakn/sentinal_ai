"""
Tests for src/ml/trainer.py

Verifies:
- make_splits produces correct sizes and disjoint sets
- Stratification preserves approximate fraud rate across splits
- train() succeeds on small fixture and returns expected keys
- Artifacts are saved to disk
- Loaded artifacts produce identical predictions to in-memory model
- Leakage prevention: test set not seen during training
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from ml.trainer import make_splits, train, load_artifacts, MODEL_VERSION


class TestMakeSplits:
    def test_total_rows_preserved(self, small_ieee_cis_fixture):
        X, y = small_ieee_cis_fixture
        X_train, X_val, X_test, y_train, y_val, y_test = make_splits(X, y)
        total = len(X_train) + len(X_val) + len(X_test)
        assert total == len(X), f"Total after split ({total}) != original ({len(X)})"

    def test_no_overlap_between_splits(self, small_ieee_cis_fixture):
        X, y = small_ieee_cis_fixture
        X_train, X_val, X_test, y_train, y_val, y_test = make_splits(X, y)
        train_idx = set(X_train.index)
        val_idx = set(X_val.index)
        test_idx = set(X_test.index)
        assert train_idx.isdisjoint(val_idx), "Train and val overlap"
        assert train_idx.isdisjoint(test_idx), "Train and test overlap"
        assert val_idx.isdisjoint(test_idx), "Val and test overlap"

    def test_stratification_roughly_preserved(self, small_ieee_cis_fixture):
        X, y = small_ieee_cis_fixture
        _, _, _, y_train, y_val, y_test = make_splits(X, y)
        base_rate = y.mean()
        for split_y, name in [(y_train, "train"), (y_val, "val"), (y_test, "test")]:
            assert abs(split_y.mean() - base_rate) < 0.05, (
                f"{name} fraud rate {split_y.mean():.3f} deviates from base {base_rate:.3f}"
            )

    def test_test_size_fraction(self, small_ieee_cis_fixture):
        X, y = small_ieee_cis_fixture
        X_train, X_val, X_test, *_ = make_splits(X, y, test_size=0.20)
        expected_test = int(len(X) * 0.20)
        assert abs(len(X_test) - expected_test) <= 2  # allow ±2 for rounding


class TestTrainOnFixture:
    def test_train_returns_expected_keys(self, small_ieee_cis_fixture, tmp_path):
        X, y = small_ieee_cis_fixture
        results = train(X, y, model_dir=tmp_path / "models/xgboost")
        required_keys = {
            "X_train", "X_val", "X_test", "y_train", "y_val", "y_test",
            "X_train_t", "X_val_t", "X_test_t",
            "model", "pipeline", "feature_names", "artifact_dir",
        }
        assert required_keys.issubset(results.keys())

    def test_artifacts_saved_to_disk(self, small_ieee_cis_fixture, tmp_path):
        X, y = small_ieee_cis_fixture
        model_dir = tmp_path / "models/xgboost"
        results = train(X, y, model_dir=model_dir)
        artifact_dir = results["artifact_dir"]
        for fname in ["preprocessor.joblib", "xgb_model.joblib", "feature_names.joblib", "metadata.json"]:
            assert (artifact_dir / fname).exists(), f"Missing artifact: {fname}"

    def test_metadata_json_structure(self, small_ieee_cis_fixture, tmp_path):
        X, y = small_ieee_cis_fixture
        model_dir = tmp_path / "models/xgboost"
        results = train(X, y, model_dir=model_dir)
        artifact_dir = results["artifact_dir"]
        with open(artifact_dir / "metadata.json") as f:
            metadata = json.load(f)
        assert "model_version" in metadata
        assert "trained_at_utc" in metadata
        assert "hyperparams" in metadata
        assert "data_stats" in metadata
        assert "classification_threshold" in metadata

    def test_model_predicts_on_test_set(self, small_ieee_cis_fixture, tmp_path):
        X, y = small_ieee_cis_fixture
        results = train(X, y, model_dir=tmp_path / "models/xgboost")
        model = results["model"]
        X_test_t = results["X_test_t"]
        probas = model.predict_proba(X_test_t)[:, 1]
        assert len(probas) == len(results["y_test"])
        assert (probas >= 0).all() and (probas <= 1).all()

    def test_test_set_not_seen_during_train(self, small_ieee_cis_fixture, tmp_path):
        """Test indices must be disjoint from train and val indices."""
        X, y = small_ieee_cis_fixture
        results = train(X, y, model_dir=tmp_path / "models/xgboost")
        train_idx = set(results["X_train"].index)
        val_idx = set(results["X_val"].index)
        test_idx = set(results["X_test"].index)
        assert train_idx.isdisjoint(test_idx), "Test leaks into training set"
        assert val_idx.isdisjoint(test_idx), "Test leaks into validation set"


class TestArtifactPersistenceAndReload:
    def test_reload_predictions_match_original(self, small_ieee_cis_fixture, tmp_path):
        """Predictions before and after saving must be bit-identical (or very close)."""
        X, y = small_ieee_cis_fixture
        model_dir = tmp_path / "models/xgboost"
        results = train(X, y, model_dir=model_dir)
        original_probas = results["model"].predict_proba(results["X_test_t"])[:, 1]

        loaded = load_artifacts(model_dir=model_dir)
        reloaded_probas = loaded["model"].predict_proba(results["X_test_t"])[:, 1]

        max_diff = float(np.abs(original_probas - reloaded_probas).max())
        assert max_diff < 1e-6, f"Prediction mismatch after reload: max_diff={max_diff}"

    def test_reload_feature_names_match(self, small_ieee_cis_fixture, tmp_path):
        X, y = small_ieee_cis_fixture
        model_dir = tmp_path / "models/xgboost"
        results = train(X, y, model_dir=model_dir)
        loaded = load_artifacts(model_dir=model_dir)
        assert results["feature_names"] == loaded["feature_names"]

    def test_load_artifacts_raises_on_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Artifact not found"):
            load_artifacts(model_dir=tmp_path / "nonexistent")
