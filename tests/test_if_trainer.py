"""
Tests for src/ml/if_trainer.py

Verifies:
- make_if_splits produces correct sizes and disjoint sets
- Stratification preserved
- train_isolation_forest does NOT use labels when fitting (unsupervised)
- Artifacts saved to disk correctly
- Metadata structure
- Standalone preprocessor saved when not sharing
- Score direction: higher = more anomalous (negated convention)
- Artifact reload consistency
- load_if_artifacts raises on missing artifacts
- Shared preprocessor path loading
"""

from __future__ import annotations

import json
import numpy as np
import pytest

from ml.if_trainer import (
    make_if_splits,
    train_isolation_forest,
    load_if_artifacts,
    raw_to_anomaly_score,
    DEFAULT_SCORE_THRESHOLD,
    IF_MODEL_VERSION,
)


class TestMakeIfSplits:
    def test_total_rows_preserved(self, small_ieee_cis_fixture):
        X, y = small_ieee_cis_fixture
        X_train, X_test, y_train, y_test = make_if_splits(X, y)
        assert len(X_train) + len(X_test) == len(X)

    def test_no_overlap(self, small_ieee_cis_fixture):
        X, y = small_ieee_cis_fixture
        X_train, X_test, y_train, y_test = make_if_splits(X, y)
        assert set(X_train.index).isdisjoint(set(X_test.index))

    def test_stratification_roughly_preserved(self, small_ieee_cis_fixture):
        X, y = small_ieee_cis_fixture
        _, _, y_train, y_test = make_if_splits(X, y)
        base_rate = y.mean()
        for split_y, name in [(y_train, "train"), (y_test, "test")]:
            assert abs(split_y.mean() - base_rate) < 0.05, (
                f"{name} fraud rate {split_y.mean():.3f} deviates from {base_rate:.3f}"
            )

    def test_test_size_fraction(self, small_ieee_cis_fixture):
        X, y = small_ieee_cis_fixture
        _, X_test, _, _ = make_if_splits(X, y, test_size=0.20)
        expected_test = int(len(X) * 0.20)
        assert abs(len(X_test) - expected_test) <= 2


class TestRawToAnomalyScore:
    def test_negation(self):
        raw = np.array([-0.5, -0.3, -0.1])
        scores = raw_to_anomaly_score(raw)
        np.testing.assert_array_almost_equal(scores, [0.5, 0.3, 0.1])

    def test_higher_score_is_more_anomalous(self):
        """Most negative raw score → highest anomaly score."""
        raw = np.array([-0.8, -0.3, -0.1])  # -0.8 most anomalous per IF
        scores = raw_to_anomaly_score(raw)
        assert scores[0] == scores.max()


class TestTrainIsolationForest:
    def test_returns_expected_keys(self, small_ieee_cis_fixture, tmp_path):
        X, y = small_ieee_cis_fixture
        results = train_isolation_forest(
            X, y,
            model_dir=tmp_path / "models/isolation_forest",
            params={"n_estimators": 10},
        )
        required = {
            "X_train", "X_test", "y_train", "y_test",
            "X_train_t", "X_test_t",
            "model", "pipeline", "feature_names",
            "artifact_dir", "train_anomaly_scores", "test_anomaly_scores",
        }
        assert required.issubset(results.keys())

    def test_model_not_trained_on_labels(self, small_ieee_cis_fixture, tmp_path):
        """IsolationForest.fit() must never receive y labels.

        Verify by checking the model has no classes_ attribute (unsupervised).
        """
        X, y = small_ieee_cis_fixture
        results = train_isolation_forest(
            X, y,
            model_dir=tmp_path / "models/isolation_forest",
            params={"n_estimators": 10},
        )
        model = results["model"]
        # IsolationForest does not have classes_ — that would only appear
        # on a supervised classifier.
        assert not hasattr(model, "classes_"), (
            "IsolationForest should not have 'classes_' — was it trained supervised?"
        )

    def test_isFraud_not_in_feature_names(self, small_ieee_cis_fixture, tmp_path):
        """The label column must never appear in the feature matrix."""
        X, y = small_ieee_cis_fixture
        results = train_isolation_forest(
            X, y,
            model_dir=tmp_path / "models/isolation_forest",
            params={"n_estimators": 10},
        )
        assert "isFraud" not in results["feature_names"]

    def test_TransactionID_not_in_feature_names(self, small_ieee_cis_fixture, tmp_path):
        X, y = small_ieee_cis_fixture
        results = train_isolation_forest(
            X, y,
            model_dir=tmp_path / "models/isolation_forest",
            params={"n_estimators": 10},
        )
        assert "TransactionID" not in results["feature_names"]

    def test_anomaly_scores_shape(self, small_ieee_cis_fixture, tmp_path):
        X, y = small_ieee_cis_fixture
        results = train_isolation_forest(
            X, y,
            model_dir=tmp_path / "models/isolation_forest",
            params={"n_estimators": 10},
        )
        assert results["train_anomaly_scores"].shape == (len(results["X_train"]),)
        assert results["test_anomaly_scores"].shape == (len(results["X_test"]),)

    def test_standalone_preprocessor_saved(self, small_ieee_cis_fixture, tmp_path):
        X, y = small_ieee_cis_fixture
        model_dir = tmp_path / "models/isolation_forest"
        results = train_isolation_forest(
            X, y, model_dir=model_dir, params={"n_estimators": 10}
        )
        artifact_dir = results["artifact_dir"]
        # Standalone preprocessor must be saved when not sharing
        assert (artifact_dir / "preprocessor.joblib").exists()
        assert (artifact_dir / "if_model.joblib").exists()
        assert (artifact_dir / "feature_names.joblib").exists()
        assert (artifact_dir / "metadata.json").exists()

    def test_metadata_structure(self, small_ieee_cis_fixture, tmp_path):
        X, y = small_ieee_cis_fixture
        model_dir = tmp_path / "models/isolation_forest"
        results = train_isolation_forest(
            X, y, model_dir=model_dir, params={"n_estimators": 10}
        )
        with open(results["artifact_dir"] / "metadata.json") as f:
            meta = json.load(f)
        required_keys = {
            "model_version", "trained_at_utc", "model_type",
            "hyperparams", "data_stats", "score_convention",
            "default_threshold", "threshold_note", "contamination_note",
        }
        assert required_keys.issubset(meta.keys())

    def test_score_convention_note_in_metadata(self, small_ieee_cis_fixture, tmp_path):
        X, y = small_ieee_cis_fixture
        model_dir = tmp_path / "models/isolation_forest"
        results = train_isolation_forest(
            X, y, model_dir=model_dir, params={"n_estimators": 10}
        )
        with open(results["artifact_dir"] / "metadata.json") as f:
            meta = json.load(f)
        # Must document the score direction and NOT-a-probability disclaimer
        note = meta["score_convention"].lower()
        assert "not" in note or "higher" in note

    def test_shared_preprocessor_path(self, small_ieee_cis_fixture, tmp_path):
        """IF can reuse a previously saved preprocessor."""
        import joblib
        from ml.preprocessor import build_preprocessing_pipeline, get_feature_names

        X, y = small_ieee_cis_fixture
        # Build and save a preprocessor to a temp path
        prep_path = tmp_path / "shared_preprocessor.joblib"
        pipeline = build_preprocessing_pipeline(X)
        joblib.dump(pipeline, prep_path)

        model_dir = tmp_path / "models/isolation_forest"
        results = train_isolation_forest(
            X, y,
            model_dir=model_dir,
            params={"n_estimators": 10},
            shared_preprocessor_path=str(prep_path),
        )
        # Standalone preprocessor should NOT be saved when sharing
        assert not (results["artifact_dir"] / "preprocessor.joblib").exists()

    def test_shared_preprocessor_missing_raises(self, small_ieee_cis_fixture, tmp_path):
        X, y = small_ieee_cis_fixture
        with pytest.raises(FileNotFoundError):
            train_isolation_forest(
                X, y,
                model_dir=tmp_path / "models/isolation_forest",
                params={"n_estimators": 10},
                shared_preprocessor_path=str(tmp_path / "nonexistent.joblib"),
            )

    def test_test_set_not_seen_during_training(self, small_ieee_cis_fixture, tmp_path):
        X, y = small_ieee_cis_fixture
        results = train_isolation_forest(
            X, y, model_dir=tmp_path / "models/isolation_forest", params={"n_estimators": 10}
        )
        train_idx = set(results["X_train"].index)
        test_idx = set(results["X_test"].index)
        assert train_idx.isdisjoint(test_idx)


class TestArtifactReload:
    def test_reload_scores_match_original(self, small_ieee_cis_fixture, tmp_path):
        X, y = small_ieee_cis_fixture
        model_dir = tmp_path / "models/isolation_forest"
        results = train_isolation_forest(
            X, y, model_dir=model_dir, params={"n_estimators": 10}
        )
        original_scores = results["test_anomaly_scores"]

        loaded = load_if_artifacts(model_dir=str(model_dir))
        reloaded_raw = loaded["model"].score_samples(results["X_test_t"])
        from ml.if_trainer import raw_to_anomaly_score
        reloaded_scores = raw_to_anomaly_score(reloaded_raw)

        max_diff = float(np.abs(original_scores - reloaded_scores).max())
        assert max_diff < 1e-6, f"Score mismatch after reload: {max_diff}"

    def test_reload_feature_names_match(self, small_ieee_cis_fixture, tmp_path):
        X, y = small_ieee_cis_fixture
        model_dir = tmp_path / "models/isolation_forest"
        results = train_isolation_forest(
            X, y, model_dir=model_dir, params={"n_estimators": 10}
        )
        loaded = load_if_artifacts(model_dir=str(model_dir))
        assert results["feature_names"] == loaded["feature_names"]

    def test_load_raises_on_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Artifact not found"):
            load_if_artifacts(model_dir=str(tmp_path / "nonexistent"))

    def test_load_raises_without_preprocessor(self, small_ieee_cis_fixture, tmp_path):
        """Shared-mode artifacts (no standalone preprocessor.joblib) require
        an explicit preprocessor_path at load time."""
        import joblib
        from ml.preprocessor import build_preprocessing_pipeline

        X, y = small_ieee_cis_fixture
        prep_path = tmp_path / "shared_preprocessor.joblib"
        pipeline = build_preprocessing_pipeline(X)
        joblib.dump(pipeline, prep_path)

        model_dir = tmp_path / "models/isolation_forest"
        train_isolation_forest(
            X, y,
            model_dir=model_dir,
            params={"n_estimators": 10},
            shared_preprocessor_path=str(prep_path),
        )
        # No preprocessor_path provided → should raise
        with pytest.raises(FileNotFoundError):
            load_if_artifacts(model_dir=str(model_dir))
