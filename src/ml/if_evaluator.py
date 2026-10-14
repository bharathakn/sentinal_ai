"""
Sentinel AI — Isolation Forest evaluation.

Evaluates the IF model against the held-out test split using IEEE-CIS labels.

Important caveats
-----------------
* Isolation Forest is UNSUPERVISED. It was not trained to detect fraud;
  it was trained to detect statistical anomalies.
* These evaluation metrics show how well anomaly detection correlates with
  the fraud label.  They are NOT proof that IF independently understands fraud.
* Precision/recall/F1 are computed at the selected threshold.  The threshold
  is NOT the contamination parameter — that controls the model's internal
  boundary; the evaluation threshold is applied to the negated scores.
* ROC-AUC and average precision (PR-AUC) are threshold-independent metrics
  computed over the full score range.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

logger = logging.getLogger(__name__)


def evaluate_anomaly_detector(
    y_true: np.ndarray,
    anomaly_scores: np.ndarray,
    *,
    threshold: float = 0.0,
    dataset_label: str = "test",
    save_path: str | Path | None = None,
) -> dict[str, Any]:
    """Evaluate IF anomaly scores against ground-truth fraud labels.

    Parameters
    ----------
    y_true         : ground-truth binary labels (0=legit, 1=fraud)
    anomaly_scores : negated IF scores (higher = more anomalous)
    threshold      : scores >= threshold classified as anomaly/fraud
    dataset_label  : label for logging
    save_path      : if given, write JSON results here

    Returns
    -------
    dict with all metrics and interpretation notes
    """
    y_pred = (anomaly_scores >= threshold).astype(int)

    precision = float(precision_score(y_true, y_pred, zero_division=0))
    recall = float(recall_score(y_true, y_pred, zero_division=0))
    f1 = float(f1_score(y_true, y_pred, zero_division=0))
    roc_auc = float(roc_auc_score(y_true, anomaly_scores))
    pr_auc = float(average_precision_score(y_true, anomaly_scores))
    cm = confusion_matrix(y_true, y_pred).tolist()
    report = classification_report(y_true, y_pred, target_names=["legitimate", "anomaly"], zero_division=0)

    results: dict[str, Any] = {
        "dataset": dataset_label,
        "model_type": "IsolationForest",
        "n_samples": int(len(y_true)),
        "n_fraud_actual": int(y_true.sum()),
        "fraud_rate_pct": round(float(y_true.mean()) * 100, 4),
        "threshold": threshold,
        "threshold_note": (
            "anomaly_score >= threshold is classified as anomaly. "
            "Adjust threshold on held-out data for operational requirements."
        ),
        "n_flagged_as_anomaly": int(y_pred.sum()),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "roc_auc": round(roc_auc, 4),
        "pr_auc": round(pr_auc, 4),
        "confusion_matrix": cm,
        "confusion_matrix_labels": ["legitimate", "anomaly"],
        "caveat": (
            "IsolationForest is UNSUPERVISED. Metrics show correlation between "
            "statistical anomaly and the fraud label. They are NOT proof that "
            "this model understands fraud independently."
        ),
    }

    logger.info("=== IF Evaluation results (%s) ===", dataset_label)
    logger.info("  Threshold   : %.4f", threshold)
    logger.info("  Precision   : %.4f", precision)
    logger.info("  Recall      : %.4f", recall)
    logger.info("  F1          : %.4f", f1)
    logger.info("  ROC-AUC     : %.4f", roc_auc)
    logger.info("  PR-AUC      : %.4f", pr_auc)
    logger.info("  Confusion   : %s", cm)
    logger.info("\nClassification report:\n%s", report)

    if save_path is not None:
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        logger.info("IF metrics saved to: %s", save_path)

    return results


def print_if_evaluation_report(metrics: dict[str, Any]) -> None:
    """Pretty-print IF evaluation metrics to stdout."""
    print(f"\n{'=' * 60}")
    print(f"  Isolation Forest Evaluation — {metrics['dataset'].upper()}")
    print(f"{'=' * 60}")
    print(f"  Samples            : {metrics['n_samples']:,}")
    print(f"  Actual fraud       : {metrics['n_fraud_actual']:,}  ({metrics['fraud_rate_pct']:.3f}%)")
    print(f"  Flagged as anomaly : {metrics['n_flagged_as_anomaly']:,}")
    print(f"  Threshold          : {metrics['threshold']}")
    print()
    print(f"  Precision          : {metrics['precision']:.4f}")
    print(f"  Recall             : {metrics['recall']:.4f}")
    print(f"  F1-score           : {metrics['f1_score']:.4f}")
    print(f"  ROC-AUC            : {metrics['roc_auc']:.4f}")
    print(f"  PR-AUC *           : {metrics['pr_auc']:.4f}")
    print()
    print(f"  * Threshold-independent metrics.")
    print()
    cm = metrics["confusion_matrix"]
    print("  Confusion Matrix (rows=actual, cols=predicted):")
    print(f"              Pred-Legit  Pred-Anomaly")
    print(f"  Act-Legit   {cm[0][0]:>10,}  {cm[0][1]:>12,}")
    print(f"  Act-Fraud   {cm[1][0]:>10,}  {cm[1][1]:>12,}")
    print()
    print(f"  NOTE: {metrics['caveat']}")
    print(f"{'=' * 60}\n")
