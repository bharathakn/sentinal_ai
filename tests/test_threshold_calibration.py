"""
Tests for src/ml/threshold_calibration.py

Verifies:
- sweep_thresholds returns correct columns and shape
- Test-set protection (raises on dataset_label='test')
- Metrics computed correctly at each threshold
- select_threshold picks correctly for each objective
- Default candidates differ by model type
- save_threshold_report writes valid JSON
- print_sweep_summary does not raise
- Custom candidates override defaults
- VALID_OBJECTIVES enforced
"""

from __future__ import annotations

import json
import numpy as np
import pytest

from ml.threshold_calibration import (
    sweep_thresholds,
    select_threshold,
    save_threshold_report,
    print_sweep_summary,
    VALID_OBJECTIVES,
)


@pytest.fixture
def binary_fixture():
    """Simple fixture: 200 samples, 10% fraud, scores correlated with labels."""
    rng = np.random.RandomState(99)
    y = (rng.random(200) < 0.10).astype(int)
    scores = np.where(y == 1, rng.uniform(0.4, 0.9, 200), rng.uniform(0.0, 0.6, 200))
    return y, scores


class TestSweepThresholds:
    def test_returns_dataframe_with_required_columns(self, binary_fixture):
        y, scores = binary_fixture
        df = sweep_thresholds(y, scores, dataset_label="validation")
        required = {"threshold", "precision", "recall", "f1", "fpr", "fnr", "n_flagged"}
        assert required.issubset(df.columns)

    def test_sorted_by_f1_descending(self, binary_fixture):
        y, scores = binary_fixture
        df = sweep_thresholds(y, scores, dataset_label="validation")
        assert list(df["f1"]) == sorted(df["f1"], reverse=True)

    def test_raises_on_test_label(self, binary_fixture):
        y, scores = binary_fixture
        with pytest.raises(ValueError, match="validation split"):
            sweep_thresholds(y, scores, dataset_label="test")

    def test_custom_candidates_used(self, binary_fixture):
        y, scores = binary_fixture
        candidates = [0.3, 0.5, 0.7]
        df = sweep_thresholds(y, scores, candidates=candidates, dataset_label="validation")
        assert len(df) == 3
        assert set(df["threshold"]) == {0.3, 0.5, 0.7}

    def test_xgboost_default_candidates_differ_from_iforest(self, binary_fixture):
        y, scores = binary_fixture
        df_xgb = sweep_thresholds(y, scores, model_type="xgboost", dataset_label="validation")
        df_if = sweep_thresholds(y, scores, model_type="iforest", dataset_label="validation")
        # Different number of defaults
        assert len(df_xgb) != len(df_if) or set(df_xgb["threshold"]) != set(df_if["threshold"])

    def test_metrics_in_range(self, binary_fixture):
        y, scores = binary_fixture
        df = sweep_thresholds(y, scores, dataset_label="validation")
        for col in ("precision", "recall", "f1", "fpr", "fnr"):
            assert (df[col] >= 0.0).all() and (df[col] <= 1.0).all(), f"{col} out of range"

    def test_fpr_computed_from_cm(self, binary_fixture):
        """Verify FPR = FP / (FP + TN) against row values."""
        y, scores = binary_fixture
        df = sweep_thresholds(y, scores, candidates=[0.5], dataset_label="validation")
        row = df.iloc[0]
        expected_fpr = round(row["fp"] / (row["fp"] + row["tn"]) if (row["fp"] + row["tn"]) > 0 else 0.0, 6)
        assert row["fpr"] == pytest.approx(expected_fpr)

    def test_fnr_computed_from_cm(self, binary_fixture):
        """Verify FNR = FN / (FN + TP)."""
        y, scores = binary_fixture
        df = sweep_thresholds(y, scores, candidates=[0.5], dataset_label="validation")
        row = df.iloc[0]
        expected_fnr = round(row["fn"] / (row["fn"] + row["tp"]) if (row["fn"] + row["tp"]) > 0 else 0.0, 6)
        assert row["fnr"] == pytest.approx(expected_fnr)

    def test_high_threshold_fewer_flagged(self, binary_fixture):
        y, scores = binary_fixture
        df = sweep_thresholds(
            y, scores, candidates=[0.2, 0.8], dataset_label="validation"
        ).sort_values("threshold")
        assert df.iloc[1]["n_flagged"] <= df.iloc[0]["n_flagged"]


class TestSelectThreshold:
    def test_default_objective_is_f1(self, binary_fixture):
        y, scores = binary_fixture
        df = sweep_thresholds(y, scores, dataset_label="validation")
        result = select_threshold(df)
        assert result["objective"] == "f1"

    def test_f1_objective_picks_best_f1(self, binary_fixture):
        y, scores = binary_fixture
        df = sweep_thresholds(y, scores, dataset_label="validation")
        result = select_threshold(df, objective="f1")
        assert result["f1"] == df["f1"].max()

    def test_precision_objective(self, binary_fixture):
        y, scores = binary_fixture
        df = sweep_thresholds(y, scores, dataset_label="validation")
        result = select_threshold(df, objective="precision")
        assert result["precision"] == df["precision"].max()

    def test_recall_objective(self, binary_fixture):
        y, scores = binary_fixture
        df = sweep_thresholds(y, scores, dataset_label="validation")
        result = select_threshold(df, objective="recall")
        assert result["recall"] == df["recall"].max()

    def test_result_keys(self, binary_fixture):
        y, scores = binary_fixture
        df = sweep_thresholds(y, scores, dataset_label="validation")
        result = select_threshold(df)
        required = {"threshold", "precision", "recall", "f1", "fpr", "fnr", "objective", "selection_note", "full_table"}
        assert required.issubset(result.keys())

    def test_selection_note_mentions_validation(self, binary_fixture):
        y, scores = binary_fixture
        df = sweep_thresholds(y, scores, dataset_label="validation")
        result = select_threshold(df)
        assert "VALIDATION" in result["selection_note"].upper() or "validation" in result["selection_note"].lower()

    def test_invalid_objective_raises(self, binary_fixture):
        y, scores = binary_fixture
        df = sweep_thresholds(y, scores, dataset_label="validation")
        with pytest.raises(ValueError, match="objective"):
            select_threshold(df, objective="nonsense")

    def test_full_table_present(self, binary_fixture):
        y, scores = binary_fixture
        df = sweep_thresholds(y, scores, dataset_label="validation")
        result = select_threshold(df)
        assert isinstance(result["full_table"], list)
        assert len(result["full_table"]) == len(df)


class TestSaveThresholdReport:
    def test_saves_valid_json(self, binary_fixture, tmp_path):
        y, scores = binary_fixture
        df = sweep_thresholds(y, scores, dataset_label="validation")
        result = select_threshold(df)
        path = tmp_path / "threshold.json"
        save_threshold_report(result, path)
        assert path.exists()
        with open(path) as f:
            data = json.load(f)
        assert "threshold" in data
        assert "selection_note" in data

    def test_full_table_not_in_saved_file(self, binary_fixture, tmp_path):
        """full_table is in-memory only, not serialized."""
        y, scores = binary_fixture
        df = sweep_thresholds(y, scores, dataset_label="validation")
        result = select_threshold(df)
        path = tmp_path / "threshold.json"
        save_threshold_report(result, path)
        with open(path) as f:
            data = json.load(f)
        assert "full_table" not in data


class TestPrintSweepSummary:
    def test_does_not_raise(self, binary_fixture, capsys):
        y, scores = binary_fixture
        df = sweep_thresholds(y, scores, dataset_label="validation")
        print_sweep_summary(df)
        out = capsys.readouterr().out
        assert "Threshold" in out
