"""
Sentinel AI — Threshold calibration runner.

Runs threshold calibration for XGBoost and Isolation Forest using the
held-out validation split from the existing trained model artifacts.

Rules
-----
* Validation split is reconstructed using the same random seed as training.
* Test set is NOT touched during threshold selection.
* The calibrated threshold is evaluated ONCE on the test set after selection.
* Results are saved versioned alongside the existing artifact, not overwriting.

Usage
-----
    python scripts/run_threshold_calibration.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
import pandas as pd
import joblib

from ml.ieee_cis_loader import load_ieee_cis
from ml.trainer import make_splits, load_artifacts
from ml.if_trainer import make_if_splits, load_if_artifacts, raw_to_anomaly_score
from ml.evaluator import evaluate, print_evaluation_report
from ml.if_evaluator import evaluate_anomaly_detector, print_if_evaluation_report
from ml.threshold_calibration import (
    sweep_thresholds,
    select_threshold,
    save_threshold_report,
    print_sweep_summary,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def calibrate_xgboost(sample_frac: float = 0.15) -> None:
    """Calibrate XGBoost classification threshold."""
    logger.info("=== XGBoost Threshold Calibration ===")

    # Reconstruct the same split used during training
    logger.info("Loading IEEE-CIS dataset (%.0f%% sample) …", sample_frac * 100)
    X, y = load_ieee_cis(data_dir="dataset/raw/ieee_cis", sample_frac=sample_frac)

    # Same split params as trainer.py defaults
    X_train, X_val, X_test, y_train, y_val, y_test = make_splits(X, y)
    logger.info("Reconstruction: train=%d, val=%d, test=%d", len(y_train), len(y_val), len(y_test))

    # Load trained artifacts
    artifacts = load_artifacts()
    pipeline = artifacts["pipeline"]
    model = artifacts["model"]
    metadata = artifacts["metadata"]

    # Transform validation and test sets
    X_val_t = pipeline.transform(X_val)
    X_test_t = pipeline.transform(X_test)

    # Validation probabilities
    val_proba = model.predict_proba(X_val_t)[:, 1]
    test_proba = model.predict_proba(X_test_t)[:, 1]

    # --- Sweep thresholds on VALIDATION ---
    logger.info("Sweeping thresholds on validation split …")
    sweep_df = sweep_thresholds(
        y_val.values, val_proba,
        model_type="xgboost",
        dataset_label="validation",
    )
    print_sweep_summary(sweep_df)

    # --- Select threshold ---
    chosen = select_threshold(sweep_df, objective="f1")
    logger.info(
        "Chosen threshold=%.4f (F1=%.4f, precision=%.4f, recall=%.4f)",
        chosen["threshold"], chosen["f1"], chosen["precision"], chosen["recall"],
    )

    # --- Evaluate on validation at chosen threshold (for report) ---
    val_metrics_calibrated = evaluate(
        y_val.values, val_proba,
        threshold=chosen["threshold"],
        dataset_label="validation",
        model_version=metadata.get("model_version"),
        split_strategy="stratified 80/10/10 (15% IEEE-CIS sample)",
    )
    print_evaluation_report(val_metrics_calibrated)

    # --- ONCE: evaluate on held-out TEST at chosen threshold ---
    logger.info("=== Final evaluation on held-out test set (chosen threshold=%.4f) ===", chosen["threshold"])
    test_metrics_calibrated = evaluate(
        y_test.values, test_proba,
        threshold=chosen["threshold"],
        dataset_label="test",
        model_version=metadata.get("model_version"),
        split_strategy="stratified 80/10/10 (15% IEEE-CIS sample)",
    )
    print_evaluation_report(test_metrics_calibrated)

    # --- Save results (without overwriting historical 0.5-threshold results) ---
    artifact_dir = Path("models/xgboost/v1")
    import json
    with open(artifact_dir / "evaluation_val_calibrated.json", "w") as f:
        json.dump(val_metrics_calibrated, f, indent=2)
    with open(artifact_dir / "evaluation_test_calibrated.json", "w") as f:
        json.dump(test_metrics_calibrated, f, indent=2)
    save_threshold_report(chosen, artifact_dir / "threshold_calibration.json")

    logger.info(
        "XGBoost calibration complete. Results saved to %s", artifact_dir
    )
    logger.info(
        "  Baseline (threshold=0.5):   F1=%.4f, Precision=%.4f, Recall=%.4f",
        0.4946, 0.3748, 0.7270,
    )
    logger.info(
        "  Calibrated (threshold=%.4f): F1=%.4f, Precision=%.4f, Recall=%.4f",
        chosen["threshold"],
        test_metrics_calibrated["f1_score"],
        test_metrics_calibrated["precision"],
        test_metrics_calibrated["recall"],
    )


def calibrate_iforest(sample_frac: float = 0.15) -> None:
    """Calibrate Isolation Forest anomaly score threshold."""
    logger.info("=== Isolation Forest Threshold Calibration ===")

    logger.info("Loading IEEE-CIS dataset (%.0f%% sample) …", sample_frac * 100)
    X, y = load_ieee_cis(data_dir="dataset/raw/ieee_cis", sample_frac=sample_frac)

    # Same split as if_trainer.py
    X_train, X_test, y_train, y_test = make_if_splits(X, y)

    # IF doesn't have a validation split — use a held-out subset of train for threshold only
    # Split train further 90/10 to get a threshold-calibration set
    from sklearn.model_selection import train_test_split
    X_train2, X_cal, y_train2, y_cal = train_test_split(
        X_train, y_train, test_size=0.10, random_state=42, stratify=y_train
    )
    logger.info(
        "IF calibration split — train2=%d, calibration=%d, test=%d",
        len(y_train2), len(y_cal), len(y_test),
    )

    # Load IF artifacts
    artifacts = load_if_artifacts(preprocessor_path="models/isolation_forest/v1/preprocessor.joblib")
    pipeline = artifacts["pipeline"]
    model = artifacts["model"]
    metadata = artifacts["metadata"]

    # Score calibration and test sets
    X_cal_t = pipeline.transform(X_cal)
    X_test_t = pipeline.transform(X_test)

    cal_scores = raw_to_anomaly_score(model.score_samples(X_cal_t))
    test_scores = raw_to_anomaly_score(model.score_samples(X_test_t))

    logger.info(
        "Calibration score stats — mean=%.4f, p50=%.4f, p90=%.4f, p95=%.4f, p99=%.4f",
        cal_scores.mean(),
        float(np.percentile(cal_scores, 50)),
        float(np.percentile(cal_scores, 90)),
        float(np.percentile(cal_scores, 95)),
        float(np.percentile(cal_scores, 99)),
    )

    # Sweep thresholds over the score distribution
    p90 = float(np.percentile(cal_scores, 90))
    p99 = float(np.percentile(cal_scores, 99))
    candidates = [round(p, 4) for p in np.linspace(p90, p99, 20)]

    logger.info("Sweeping IF thresholds from %.4f to %.4f …", p90, p99)
    sweep_df = sweep_thresholds(
        y_cal.values, cal_scores,
        model_type="iforest",
        candidates=candidates,
        dataset_label="validation",
    )
    print_sweep_summary(sweep_df)

    chosen = select_threshold(sweep_df, objective="f1")
    logger.info(
        "IF chosen threshold=%.4f (F1=%.4f, precision=%.4f, recall=%.4f)",
        chosen["threshold"], chosen["f1"], chosen["precision"], chosen["recall"],
    )

    # Final evaluation on test set
    logger.info("=== IF Final evaluation on held-out test set (threshold=%.4f) ===", chosen["threshold"])
    test_metrics = evaluate_anomaly_detector(
        y_test.values, test_scores,
        threshold=chosen["threshold"],
        dataset_label="test",
        save_path="models/isolation_forest/v1/evaluation_test_calibrated.json",
    )
    print_if_evaluation_report(test_metrics)

    save_threshold_report(chosen, "models/isolation_forest/v1/threshold_calibration.json")

    logger.info(
        "IF calibration complete. Results saved to models/isolation_forest/v1/"
    )
    logger.info(
        "  Trivial threshold=0.0:         FPR=1.000, FNR=0.000 (all flagged)"
    )
    logger.info(
        "  Calibrated (threshold=%.4f): FPR=%.4f, FNR=%.4f, F1=%.4f",
        chosen["threshold"],
        test_metrics["false_positive_rate"],
        test_metrics["false_negative_rate"],
        test_metrics["f1_score"],
    )


if __name__ == "__main__":
    calibrate_xgboost()
    calibrate_iforest()
