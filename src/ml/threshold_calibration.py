"""
Sentinel AI — Classification threshold calibration.

Purpose
-------
Sweep candidate thresholds on the VALIDATION split to find an operational
threshold for either the XGBoost (probability) or Isolation Forest (anomaly
score) models, then evaluate the chosen threshold ONCE on the held-out test set.

Design rules
------------
* Threshold selection uses ONLY the validation split. Never the test set.
* The test set is evaluated ONCE after a threshold is selected. Do not loop
  over the test set to pick a threshold.
* No single universally optimal threshold exists. The choice depends on the
  operational cost of false positives versus false negatives. Where no cost
  function is available, F1-maximisation is used as a defensible default and
  the full precision/recall trade-off is documented.
* Results are saved separately from the original 0.5-threshold results to
  preserve the historical baseline.
* A threshold is NOT the same as the IsolationForest ``contamination``
  parameter. They are conceptually separate.

Usage
-----
XGBoost:

    from src.ml.threshold_calibration import sweep_thresholds, select_threshold

    table = sweep_thresholds(y_val, val_proba, model_type="xgboost")
    chosen = select_threshold(table, objective="f1")
    print(chosen)

Isolation Forest:

    table = sweep_thresholds(y_val, val_anomaly_scores, model_type="iforest")
    chosen = select_threshold(table, objective="f1")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

logger = logging.getLogger(__name__)

# Thresholds to evaluate
_DEFAULT_XGB_CANDIDATES = np.round(np.arange(0.05, 0.96, 0.05), 2).tolist()
_DEFAULT_IF_CANDIDATES = np.round(np.arange(0.30, 0.75, 0.02), 2).tolist()

VALID_OBJECTIVES = {"f1", "precision", "recall", "balanced_f1"}


def sweep_thresholds(
    y_true: np.ndarray,
    scores: np.ndarray,
    *,
    model_type: str = "xgboost",
    candidates: list[float] | None = None,
    dataset_label: str = "validation",
) -> pd.DataFrame:
    """Evaluate candidate thresholds on a labelled split.

    Parameters
    ----------
    y_true      : ground-truth binary labels (0/1)
    scores      : fraud probabilities (XGBoost) or anomaly scores (IF).
                  Both conventions: higher = greater concern.
    model_type  : 'xgboost' or 'iforest' — controls default candidates and labels
    candidates  : explicit list of thresholds to evaluate.  Defaults to a
                  sensible range for each model type.
    dataset_label : label for metadata (should be 'validation', never 'test')

    Returns
    -------
    pd.DataFrame with one row per threshold and columns:
        threshold, precision, recall, f1, fpr, fnr, n_flagged
    Sorted descending by f1.

    Notes
    -----
    ROC-AUC and PR-AUC are threshold-independent and are not included here.
    Compute them once with the evaluator module.
    """
    if dataset_label == "test":
        raise ValueError(
            "Threshold calibration must use the validation split, not the test set. "
            "Set dataset_label='validation' and pass validation-set labels and scores."
        )

    if candidates is None:
        candidates = (
            _DEFAULT_XGB_CANDIDATES
            if model_type == "xgboost"
            else _DEFAULT_IF_CANDIDATES
        )

    rows = []
    for thr in candidates:
        y_pred = (scores >= thr).astype(int)
        cm = confusion_matrix(y_true, y_pred).tolist()
        tn, fp, fn, tp = cm[0][0], cm[0][1], cm[1][0], cm[1][1]

        prec = float(precision_score(y_true, y_pred, zero_division=0))
        rec = float(recall_score(y_true, y_pred, zero_division=0))
        f1 = float(f1_score(y_true, y_pred, zero_division=0))
        fpr = round(fp / (fp + tn) if (fp + tn) > 0 else 0.0, 6)
        fnr = round(fn / (fn + tp) if (fn + tp) > 0 else 0.0, 6)

        rows.append({
            "threshold": round(float(thr), 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "fpr": fpr,
            "fnr": fnr,
            "n_flagged": int(y_pred.sum()),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
        })

    df = pd.DataFrame(rows).sort_values("f1", ascending=False).reset_index(drop=True)
    logger.info(
        "Threshold sweep (%s, %s split) — %d candidates evaluated. Best F1=%.4f at threshold=%.4f",
        model_type, dataset_label, len(candidates),
        df["f1"].iloc[0], df["threshold"].iloc[0],
    )
    return df


def select_threshold(
    sweep_df: pd.DataFrame,
    *,
    objective: str = "f1",
) -> dict[str, Any]:
    """Select a threshold from a sweep table.

    Parameters
    ----------
    sweep_df  : output of sweep_thresholds()
    objective : selection criterion.
        'f1'          — maximise F1 (default; defensible without cost function)
        'precision'   — maximise precision (minimise false alarms)
        'recall'      — maximise recall (minimise missed fraud)
        'balanced_f1' — maximise F1, tie-break by balanced precision/recall

    Returns
    -------
    dict with: threshold, precision, recall, f1, fpr, fnr, objective,
               selection_note, full_table (as list of dicts)
    """
    if objective not in VALID_OBJECTIVES:
        raise ValueError(f"objective must be one of {VALID_OBJECTIVES}, got {objective!r}")

    if objective in {"f1", "balanced_f1"}:
        best_row = sweep_df.sort_values("f1", ascending=False).iloc[0]
    elif objective == "precision":
        best_row = sweep_df.sort_values("precision", ascending=False).iloc[0]
    elif objective == "recall":
        best_row = sweep_df.sort_values("recall", ascending=False).iloc[0]

    result = {
        "threshold": float(best_row["threshold"]),
        "precision": float(best_row["precision"]),
        "recall": float(best_row["recall"]),
        "f1": float(best_row["f1"]),
        "fpr": float(best_row["fpr"]),
        "fnr": float(best_row["fnr"]),
        "n_flagged": int(best_row["n_flagged"]),
        "objective": objective,
        "selection_note": (
            f"Threshold selected by maximising {objective} on the VALIDATION split. "
            "This was NOT tuned on the test set. "
            "The test set was evaluated separately, once, after threshold selection. "
            "Operational threshold should be reviewed by a domain expert — the "
            f"precision/recall trade-off depends on the cost of false alerts vs missed fraud."
        ),
        "full_table": sweep_df.to_dict(orient="records"),
    }

    logger.info(
        "Selected threshold=%.4f (objective=%s): precision=%.4f, recall=%.4f, f1=%.4f",
        result["threshold"], objective,
        result["precision"], result["recall"], result["f1"],
    )
    return result


def save_threshold_report(
    threshold_result: dict[str, Any],
    save_path: str | Path,
) -> None:
    """Save a threshold selection result dict to JSON, omitting the full table."""
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    # Save without full_table for compactness; keep it in memory only
    payload = {k: v for k, v in threshold_result.items() if k != "full_table"}
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    logger.info("Threshold report saved to: %s", save_path)


def print_sweep_summary(sweep_df: pd.DataFrame, top_n: int = 10) -> None:
    """Print the top rows of a sweep table."""
    print(f"\n{'='*70}")
    print("  Threshold Sweep — Top results by F1")
    print(f"{'='*70}")
    print(f"  {'Threshold':>10}  {'Precision':>10}  {'Recall':>8}  {'F1':>8}  {'FPR':>8}  {'FNR':>8}")
    for _, row in sweep_df.head(top_n).iterrows():
        print(
            f"  {row['threshold']:>10.4f}  {row['precision']:>10.4f}  "
            f"{row['recall']:>8.4f}  {row['f1']:>8.4f}  "
            f"{row['fpr']:>8.6f}  {row['fnr']:>8.6f}"
        )
    print(f"{'='*70}\n")
