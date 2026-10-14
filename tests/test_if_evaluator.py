"""
Tests for src/ml/if_evaluator.py

Verifies:
- All required metric keys present
- Confusion matrix is 2×2
- Threshold documented
- Metrics in valid ranges
- Caveat text present
- Save to disk works
- Dataset label in output
- Degenerate inputs do not crash
"""

from __future__ import annotations

import json
import numpy as np
import pytest

from ml.if_evaluator import evaluate_anomaly_detector, print_if_evaluation_report


@pytest.fixture
def eval_fixture():
    rng = np.random.RandomState(7)
    y_true = (rng.random(200) < 0.10).astype(int)
    # Simulate: anomalies correlate somewhat with fraud
    scores = np.where(y_true == 1, rng.uniform(0.05, 0.8, 200), rng.uniform(-0.8, 0.2, 200))
    return y_true, scores


class TestEvaluateAnomalyDetector:
    def test_required_keys_present(self, eval_fixture):
        y, scores = eval_fixture
        metrics = evaluate_anomaly_detector(y, scores)
        required = {
            "precision", "recall", "f1_score", "roc_auc", "pr_auc",
            "confusion_matrix", "threshold", "threshold_note",
            "caveat", "n_flagged_as_anomaly",
        }
        assert required.issubset(metrics.keys())

    def test_confusion_matrix_is_2x2(self, eval_fixture):
        y, scores = eval_fixture
        metrics = evaluate_anomaly_detector(y, scores)
        cm = metrics["confusion_matrix"]
        assert len(cm) == 2 and len(cm[0]) == 2 and len(cm[1]) == 2

    def test_threshold_documented(self, eval_fixture):
        y, scores = eval_fixture
        metrics = evaluate_anomaly_detector(y, scores, threshold=0.1)
        assert metrics["threshold"] == 0.1
        assert isinstance(metrics["threshold_note"], str)

    def test_metrics_in_valid_range(self, eval_fixture):
        y, scores = eval_fixture
        metrics = evaluate_anomaly_detector(y, scores)
        for key in ("precision", "recall", "f1_score", "roc_auc", "pr_auc"):
            val = metrics[key]
            assert 0.0 <= val <= 1.0, f"{key}={val} out of range"

    def test_caveat_text_present(self, eval_fixture):
        """The evaluation must include an explicit caveat that IF is unsupervised."""
        y, scores = eval_fixture
        metrics = evaluate_anomaly_detector(y, scores)
        caveat = metrics["caveat"].lower()
        assert "unsupervised" in caveat

    def test_save_to_disk(self, eval_fixture, tmp_path):
        y, scores = eval_fixture
        out_path = tmp_path / "if_metrics.json"
        evaluate_anomaly_detector(y, scores, save_path=out_path)
        assert out_path.exists()
        with open(out_path) as f:
            saved = json.load(f)
        assert "pr_auc" in saved
        assert "caveat" in saved

    def test_dataset_label_in_output(self, eval_fixture):
        y, scores = eval_fixture
        metrics = evaluate_anomaly_detector(y, scores, dataset_label="my_test")
        assert metrics["dataset"] == "my_test"

    def test_model_type_field(self, eval_fixture):
        y, scores = eval_fixture
        metrics = evaluate_anomaly_detector(y, scores)
        assert metrics["model_type"] == "IsolationForest"

    def test_all_zero_scores_do_not_crash(self):
        y = np.array([0, 1, 0, 1, 0])
        scores = np.zeros(5)
        metrics = evaluate_anomaly_detector(y, scores)
        assert "precision" in metrics

    def test_n_flagged_count(self, eval_fixture):
        y, scores = eval_fixture
        threshold = 0.0
        y_pred = (scores >= threshold).astype(int)
        metrics = evaluate_anomaly_detector(y, scores, threshold=threshold)
        assert metrics["n_flagged_as_anomaly"] == int(y_pred.sum())


class TestPrintIfReport:
    def test_print_does_not_raise(self, eval_fixture, capsys):
        y, scores = eval_fixture
        metrics = evaluate_anomaly_detector(y, scores)
        print_if_evaluation_report(metrics)
        out = capsys.readouterr().out
        assert "Precision" in out
        assert "NOTE" in out
