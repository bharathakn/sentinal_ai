"""
Sentinel AI — Model evaluation.

Calculates and reports the required fraud-detection metrics against the
held-out test split.

Metrics reported
----------------
* Accuracy
* Precision
* Recall
* F1-score
* ROC-AUC
* PR-AUC (average precision) — most informative for severe class imbalance
* Confusion matrix
* False Positive Rate (FPR = FP / (FP + TN))
* False Negative Rate (FNR = FN / (FN + TP))
* Classification threshold (explicitly documented)

Important
---------
These metrics are computed on the held-out test set that was NOT used during
training or hyperparameter tuning.  High accuracy alone is not reported as
proof of good fraud detection because the base rate is ~3.5%, meaning a
trivial all-zeros classifier already achieves >96% accuracy.

For threshold calibration, always use the VALIDATION split, not the test set.
Evaluate the chosen threshold on the test set only once (final evaluation).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

logger = logging.getLogger(__name__)


def evaluate(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    *,
    threshold: float = 0.5,
    dataset_label: str = "test",
    save_path: str | Path | None = None,
    # Optional metadata fields
    model_version: str | None = None,
    split_strategy: str | None = None,
    evaluation_date: str | None = None,
) -> dict[str, Any]:
    """Calculate and return fraud detection metrics.

    Parameters
    ----------
    y_true         : ground-truth labels (0/1)
    y_prob         : model fraud probability scores
    threshold      : classification threshold applied to probabilities
    dataset_label  : label used in log messages (e.g. 'test', 'val')
    save_path      : if given, write the metrics dict as JSON to this path
    model_version  : optional model version string to include in metadata
    split_strategy : optional description of the split strategy used
    evaluation_date: optional ISO date string; defaults to today (UTC)

    Returns
    -------
    dict with metric values, threshold documentation, and metadata
    """
    from datetime import date, timezone

    y_pred = (y_prob >= threshold).astype(int)

    accuracy = float(accuracy_score(y_true, y_pred))
    precision = float(precision_score(y_true, y_pred, zero_division=0))
    recall = float(recall_score(y_true, y_pred, zero_division=0))
    f1 = float(f1_score(y_true, y_pred, zero_division=0))
    roc_auc = float(roc_auc_score(y_true, y_prob))
    pr_auc = float(average_precision_score(y_true, y_prob))
    cm = confusion_matrix(y_true, y_pred).tolist()
    report = classification_report(y_true, y_pred, target_names=["legitimate", "fraud"], zero_division=0)

    # FPR = FP / (FP + TN),  FNR = FN / (FN + TP)
    tn, fp, fn, tp = cm[0][0], cm[0][1], cm[1][0], cm[1][1]
    fpr = round(fp / (fp + tn) if (fp + tn) > 0 else 0.0, 6)
    fnr = round(fn / (fn + tp) if (fn + tp) > 0 else 0.0, 6)

    results: dict[str, Any] = {
        # --- metadata ---
        "dataset": dataset_label,
        "model_version": model_version,
        "split_strategy": split_strategy,
        "evaluation_date": evaluation_date or str(date.today()),
        # --- sample statistics ---
        "n_samples": int(len(y_true)),
        "n_fraud": int(y_true.sum()),
        "fraud_rate_pct": round(float(y_true.mean()) * 100, 4),
        # --- threshold ---
        "threshold": threshold,
        "threshold_note": (
            "Scores >= threshold are labelled fraud. Adjust threshold on validation "
            "data to meet operational precision/recall requirements."
        ),
        # --- metrics ---
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "roc_auc": round(roc_auc, 4),
        "pr_auc": round(pr_auc, 4),
        "pr_auc_note": (
            "PR-AUC (average precision) is the primary metric for this imbalanced "
            "dataset.  ROC-AUC can be misleadingly optimistic when negatives dominate."
        ),
        "false_positive_rate": fpr,
        "false_negative_rate": fnr,
        "confusion_matrix": cm,
        "confusion_matrix_labels": ["legitimate", "fraud"],
    }

    logger.info("=== Evaluation results (%s) ===", dataset_label)
    logger.info("  Threshold        : %.4f", threshold)
    logger.info("  Accuracy         : %.4f", accuracy)
    logger.info("  Precision        : %.4f", precision)
    logger.info("  Recall           : %.4f", recall)
    logger.info("  F1               : %.4f", f1)
    logger.info("  ROC-AUC          : %.4f", roc_auc)
    logger.info("  PR-AUC           : %.4f", pr_auc)
    logger.info("  FPR              : %.6f", fpr)
    logger.info("  FNR              : %.6f", fnr)
    logger.info("  Confusion matrix : %s", cm)
    logger.info("\nClassification report:\n%s", report)

    if save_path is not None:
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        logger.info("Metrics saved to: %s", save_path)

    return results


def print_evaluation_report(metrics: dict[str, Any]) -> None:
    """Pretty-print an evaluation metrics dict to stdout."""
    print(f"\n{'=' * 60}")
    print(f"  Evaluation Report — {metrics['dataset'].upper()} SET")
    print(f"{'=' * 60}")
    print(f"  Samples          : {metrics['n_samples']:,}")
    print(f"  Fraud count      : {metrics['n_fraud']:,}  ({metrics['fraud_rate_pct']:.3f}%)")
    if metrics.get('model_version'):
        print(f"  Model version    : {metrics['model_version']}")
    if metrics.get('evaluation_date'):
        print(f"  Evaluation date  : {metrics['evaluation_date']}")
    print(f"  Threshold        : {metrics['threshold']}")
    print()
    print(f"  Accuracy         : {metrics.get('accuracy', 'N/A')}")
    print(f"  Precision        : {metrics['precision']:.4f}")
    print(f"  Recall           : {metrics['recall']:.4f}")
    print(f"  F1-score         : {metrics['f1_score']:.4f}")
    print(f"  ROC-AUC          : {metrics['roc_auc']:.4f}")
    print(f"  PR-AUC *         : {metrics['pr_auc']:.4f}")
    print(f"  False Pos. Rate  : {metrics.get('false_positive_rate', 'N/A')}")
    print(f"  False Neg. Rate  : {metrics.get('false_negative_rate', 'N/A')}")
    print()
    print(f"  * PR-AUC is the primary metric for imbalanced fraud detection.")
    print()
    cm = metrics["confusion_matrix"]
    print("  Confusion Matrix (rows=actual, cols=predicted):")
    print(f"              Pred-Legit  Pred-Fraud")
    print(f"  Act-Legit   {cm[0][0]:>10,}  {cm[0][1]:>10,}")
    print(f"  Act-Fraud   {cm[1][0]:>10,}  {cm[1][1]:>10,}")
    print(f"{'=' * 60}\n")
