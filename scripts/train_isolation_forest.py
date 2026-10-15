"""
Sentinel AI — Isolation Forest training pipeline entry point.

Usage
-----
From the repository root (with virtual environment activated):

    python scripts/train_isolation_forest.py

Optional environment variable overrides:

    SENTINEL_DATA_DIR      — IEEE-CIS dataset directory
                             (default: dataset/raw/ieee_cis)
    SENTINEL_IF_MODEL_DIR  — IF artifact directory
                             (default: models/isolation_forest)
    SENTINEL_XGB_PREP_PATH — path to existing XGBoost preprocessor.joblib
                             to reuse (e.g. models/xgboost/v1/preprocessor.joblib)
                             If not set, a standalone preprocessor is fitted.
    SENTINEL_SAMPLE_FRAC   — float in (0, 1] to subsample the dataset
                             (default: use full dataset)

Outputs
-------
    models/isolation_forest/v1/
        if_model.joblib           — fitted IsolationForest
        feature_names.joblib      — ordered feature name list
        preprocessor.joblib       — standalone preprocessor (if not shared)
        metadata.json             — version, timestamp, params, score convention
        evaluation_test.json      — held-out test metrics

Important
---------
* Isolation Forest labels are NOT fraud labels — they are anomaly labels.
  Metrics measure anomaly/fraud correlation, not independent fraud detection.
* The test set is evaluated ONCE at the end. Do not repeatedly tune against
  the test results; use validation data for threshold selection.
* Artifacts are gitignored (models/, *.joblib). Do not commit them.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ml.ieee_cis_loader import load_ieee_cis
from ml.if_trainer import train_isolation_forest, load_if_artifacts
from ml.if_evaluator import evaluate_anomaly_detector, print_if_evaluation_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    data_dir = os.environ.get("SENTINEL_DATA_DIR", "dataset/raw/ieee_cis")
    model_dir = os.environ.get("SENTINEL_IF_MODEL_DIR", "models/isolation_forest")
    xgb_prep_path = os.environ.get("SENTINEL_XGB_PREP_PATH", "") or None
    sample_frac_str = os.environ.get("SENTINEL_SAMPLE_FRAC", "")
    if sample_frac_str.strip().lower() in ("none", "full", "all"):
        sample_frac = None
    elif sample_frac_str.strip():
        sample_frac = float(sample_frac_str.strip())
    else:
        sample_frac = None

    logger.info("=== Sentinel AI — Isolation Forest Training Pipeline ===")
    logger.info("Data dir        : %s", data_dir)
    logger.info("IF model dir    : %s", model_dir)
    logger.info("XGB preprocessor: %s", xgb_prep_path or "(fit standalone)")
    logger.info("Sample frac     : %s", sample_frac or "full dataset")

    # ------------------------------------------------------------------
    # 1. Load IEEE-CIS labeled data (reuse existing loader)
    # ------------------------------------------------------------------
    logger.info("Step 1 / 4 — Loading dataset …")
    X, y = load_ieee_cis(data_dir=data_dir, sample_frac=sample_frac)

    # ------------------------------------------------------------------
    # 2. Train Isolation Forest
    # ------------------------------------------------------------------
    logger.info("Step 2 / 4 — Training Isolation Forest …")
    results = train_isolation_forest(
        X, y,
        model_dir=model_dir,
        shared_preprocessor_path=xgb_prep_path,
    )

    model = results["model"]
    artifact_dir = results["artifact_dir"]

    # ------------------------------------------------------------------
    # 3. Evaluate on held-out test set (ONCE, final)
    # ------------------------------------------------------------------
    logger.info("Step 3 / 4 — Final evaluation on held-out test set …")
    test_metrics = evaluate_anomaly_detector(
        results["y_test"].values,
        results["test_anomaly_scores"],
        dataset_label="test",
        save_path=artifact_dir / "evaluation_test.json",
    )
    print_if_evaluation_report(test_metrics)

    # ------------------------------------------------------------------
    # 4. Sanity check: reload and verify prediction consistency
    # ------------------------------------------------------------------
    logger.info("Step 4 / 4 — Reload sanity check …")
    standalone_prep = artifact_dir / "preprocessor.joblib"
    loaded = load_if_artifacts(
        model_dir=model_dir,
        preprocessor_path=str(standalone_prep) if standalone_prep.exists() else xgb_prep_path,
    )
    reloaded_raw = loaded["model"].score_samples(results["X_test_t"])
    original_raw = model.score_samples(results["X_test_t"])
    max_diff = float(abs(original_raw - reloaded_raw).max())
    if max_diff > 1e-6:
        logger.error("SCORE MISMATCH after reload! max_diff=%.8f", max_diff)
        sys.exit(1)
    logger.info("Score consistency verified. max_diff=%.2e ✓", max_diff)

    logger.info("=== IF pipeline complete. Artifacts at: %s ===", artifact_dir)


if __name__ == "__main__":
    main()
