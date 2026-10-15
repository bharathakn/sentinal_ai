"""
Sentinel AI — XGBoost training pipeline entry point.

Usage
-----
From the repository root (with the virtual environment activated):

    python scripts/train_pipeline.py

Optional arguments (set via environment variables):

    SENTINEL_DATA_DIR      — override IEEE-CIS dataset directory
                             (default: dataset/raw/ieee_cis)
    SENTINEL_MODEL_DIR     — override model artifact directory
                             (default: models/xgboost)
    SENTINEL_SAMPLE_FRAC   — float in (0, 1] to subsample the dataset
                             (default: use full dataset)

Outputs
-------
    models/xgboost/v1/
        preprocessor.joblib
        xgb_model.joblib
        feature_names.joblib
        metadata.json
    models/xgboost/v1/evaluation_test.json   — held-out test metrics
    models/xgboost/v1/evaluation_val.json    — validation metrics

Important
---------
* The held-out test set is evaluated ONCE at the end.  Do not re-run this
  script repeatedly to tune against test results; use the validation metrics.
* Model artifacts are gitignored (*.joblib, models/).  Do not commit them.
* Dataset files are gitignored (dataset/).  Do not commit them.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Ensure the src package is importable when run from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ml.ieee_cis_loader import load_ieee_cis
from ml.trainer import train, load_artifacts
from ml.evaluator import evaluate, print_evaluation_report
from ml.explainer import global_importance

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    data_dir = os.environ.get("SENTINEL_DATA_DIR", "dataset/raw/ieee_cis")
    model_dir = os.environ.get("SENTINEL_MODEL_DIR", "models/xgboost")
    sample_frac_str = os.environ.get("SENTINEL_SAMPLE_FRAC", "")
    if sample_frac_str.strip().lower() in ("none", "full", "all"):
        sample_frac = None
    elif sample_frac_str.strip():
        sample_frac = float(sample_frac_str.strip())
    else:
        sample_frac = None

    logger.info("=== Sentinel AI — XGBoost Training Pipeline ===")
    logger.info("Data dir   : %s", data_dir)
    logger.info("Model dir  : %s", model_dir)
    logger.info("Sample frac: %s", sample_frac or "full dataset")

    # ------------------------------------------------------------------
    # 1. Load IEEE-CIS labeled data
    # ------------------------------------------------------------------
    logger.info("Step 1 / 5 — Loading dataset …")
    X, y = load_ieee_cis(data_dir=data_dir, sample_frac=sample_frac)

    # ------------------------------------------------------------------
    # 2. Train (includes splitting + preprocessing + saving artifacts)
    # ------------------------------------------------------------------
    logger.info("Step 2 / 5 — Training …")
    results = train(X, y, model_dir=model_dir)

    model = results["model"]
    pipeline = results["pipeline"]
    feature_names = results["feature_names"]
    artifact_dir = results["artifact_dir"]

    # ------------------------------------------------------------------
    # 3. Evaluate on validation set
    # ------------------------------------------------------------------
    logger.info("Step 3 / 5 — Evaluating on validation set …")
    val_probas = model.predict_proba(results["X_val_t"])[:, 1]
    val_metrics = evaluate(
        results["y_val"].values,
        val_probas,
        dataset_label="validation",
        save_path=artifact_dir / "evaluation_val.json",
    )
    print_evaluation_report(val_metrics)

    # ------------------------------------------------------------------
    # 4. Evaluate on held-out test set (ONCE, final)
    # ------------------------------------------------------------------
    logger.info("Step 4 / 5 — Final evaluation on held-out test set …")
    test_probas = model.predict_proba(results["X_test_t"])[:, 1]
    test_metrics = evaluate(
        results["y_test"].values,
        test_probas,
        dataset_label="test",
        save_path=artifact_dir / "evaluation_test.json",
    )
    print_evaluation_report(test_metrics)

    # ------------------------------------------------------------------
    # 5. Global SHAP importance (sample for speed)
    # ------------------------------------------------------------------
    logger.info("Step 5 / 5 — Computing global SHAP importance …")
    importance_df = global_importance(
        model,
        results["X_train_t"],
        feature_names,
        max_display=20,
        background_sample=min(500, len(results["X_train_t"])),
    )
    importance_path = artifact_dir / "shap_global_importance.csv"
    importance_df.to_csv(importance_path, index=False)
    logger.info("SHAP global importance saved to: %s", importance_path)

    print("\nTop 10 features by mean |SHAP|:")
    print(importance_df.head(10).to_string(index=False))

    # ------------------------------------------------------------------
    # Sanity check: reload artifacts and confirm predictions match
    # ------------------------------------------------------------------
    logger.info("Sanity check — reloading artifacts and verifying predictions …")
    loaded = load_artifacts(model_dir=model_dir)
    reloaded_probas = loaded["model"].predict_proba(results["X_test_t"])[:, 1]
    max_diff = abs(test_probas - reloaded_probas).max()
    if max_diff > 1e-6:
        logger.error("PREDICTION MISMATCH after reload! max_diff=%.8f", max_diff)
        sys.exit(1)
    logger.info("Prediction consistency verified. max_diff=%.2e ✓", max_diff)

    logger.info("=== Training pipeline complete. Artifacts at: %s ===", artifact_dir)


if __name__ == "__main__":
    main()
