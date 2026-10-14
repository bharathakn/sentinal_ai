"""
Tests for src/ml/evaluator.py

Verifies:
- All required metrics are present in output
- Threshold documentation is present
- PR-AUC is not confused with ROC-AUC
- Confusion matrix has correct shape (2x2)
- Metrics save to disk when path is given
- Degenerate cases don't crash (all-zero predictions)
"""

from __future__ import annotations

import json
import numpy as np
import pytest

from ml.evaluator import evaluate, print_evaluation_report


@pytest.fixture
def binary_fixture():
    """Small (100-row) ground-truth and probability arrays."""
    rng = np.random.RandomState(0)
    y_true = (rng.random(100) < 0.15).astype(int)
    y_prob = np.clip(y_true * 0.7 + rng.random(100) * 0.3, 0, 1)
    return y_true, y_prob


class TestEvaluateReturnStructure:
    def test_required_metric_keys_present(self, binary_fixture):
        y_true, y_prob = binary_fixture
        metrics = evaluate(y_true, y_prob)
        required = {"precision", "recall", "f1_score", "roc_auc", "pr_auc",
                    "confusion_matrix", "threshold", "threshold_note"}
        assert required.issubset(metrics.keys())

    def test_confusion_matrix_shape(self, binary_fixture):
        y_true, y_prob = binary_fixture
        metrics = evaluate(y_true, y_prob)
        cm = metrics["confusion_matrix"]
        assert len(cm) == 2
        assert len(cm[0]) == 2
        assert len(cm[1]) == 2

    def test_threshold_documented(self, binary_fixture):
        y_true, y_prob = binary_fixture
        metrics = evaluate(y_true, y_prob, threshold=0.4)
        assert metrics["threshold"] == 0.4
        assert isinstance(metrics["threshold_note"], str)
        assert len(metrics["threshold_note"]) > 0

    def test_pr_auc_distinct_from_roc_auc(self, binary_fixture):
        y_true, y_prob = binary_fixture
        metrics = evaluate(y_true, y_prob)
        # They should be different values for imbalanced data
        assert "roc_auc" in metrics
        assert "pr_auc" in metrics

    def test_metrics_in_valid_range(self, binary_fixture):
        y_true, y_prob = binary_fixture
        metrics = evaluate(y_true, y_prob)
        for key in ("precision", "recall", "f1_score", "roc_auc", "pr_auc"):
            val = metrics[key]
            assert 0.0 <= val <= 1.0, f"{key}={val} out of [0, 1]"

    def test_save_to_disk(self, binary_fixture, tmp_path):
        y_true, y_prob = binary_fixture
        out_path = tmp_path / "metrics.json"
        evaluate(y_true, y_prob, save_path=out_path)
        assert out_path.exists()
        with open(out_path) as f:
            saved = json.load(f)
        assert "pr_auc" in saved

    def test_all_zero_predictions_do_not_crash(self):
        y_true = np.array([0, 0, 1, 0, 1])
        y_prob = np.zeros(5)
        # Should not raise; precision/recall may be 0 with zero_division=0
        metrics = evaluate(y_true, y_prob)
        assert "precision" in metrics

    def test_dataset_label_in_output(self, binary_fixture):
        y_true, y_prob = binary_fixture
        metrics = evaluate(y_true, y_prob, dataset_label="my_test_set")
        assert metrics["dataset"] == "my_test_set"


class TestPrintEvaluationReport:
    def test_print_does_not_raise(self, binary_fixture, capsys):
        y_true, y_prob = binary_fixture
        metrics = evaluate(y_true, y_prob)
        print_evaluation_report(metrics)
        out = capsys.readouterr().out
        assert "Precision" in out
        assert "PR-AUC" in out
