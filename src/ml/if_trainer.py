"""
Sentinel AI — Isolation Forest anomaly detection trainer.

Responsibility
--------------
Train, persist, and provide inference for an unsupervised anomaly detector
using scikit-learn's IsolationForest.

Design principles
-----------------
* Unsupervised training — fraud labels (y) are NEVER passed to IsolationForest.fit().
  Labels are held separately and used ONLY for evaluation.
* Reuses the same preprocessing pipeline as XGBoost (no second pipeline).
  If XGBoost artifacts exist on the same training split, the preprocessor
  can be loaded from there; otherwise it is built here.
* Score direction: IsolationForest.score_samples() returns lower values for
  anomalies.  This module negates the raw score so that higher → more anomalous,
  consistent with the XGBoost probability convention used elsewhere in Sentinel AI.
* Contamination parameter: deliberately NOT set to the observed fraud rate.
  The model is unsupervised — it does not know what fraction is fraudulent.
  Default 'auto' (0.1 legacy sklearn) is used; operators can override.
* Training is separate from inference; never retrain at application startup.

Score interpretation
--------------------
``anomaly_score`` ∈ ℝ:
    Higher → more anomalous.
    Values > 0 typically indicate anomalous behaviour; values < 0 are normal.
    This is NOT a probability.  Do not interpret it as "probability of fraud".

``is_anomaly`` (bool):
    True when anomaly_score >= threshold (default: 0.0, i.e. the model's
    natural decision boundary).

Artifact layout
---------------
``models/isolation_forest/v<VERSION>/``
    if_model.joblib       — fitted IsolationForest
    feature_names.joblib  — ordered feature names (must match preprocessor)
    metadata.json         — version, timestamp, hyperparams, score conventions

The preprocessing pipeline is SHARED with the XGBoost model when they are
trained on the same split.  The IF artifacts reference the XGBoost preprocessor
path rather than duplicating it.  If a standalone preprocessor is required
(different split), it is saved separately as ``preprocessor.joblib``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import train_test_split

from .preprocessor import build_preprocessing_pipeline, get_feature_names

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IF_MODEL_VERSION = "1"
DEFAULT_IF_MODEL_DIR = Path("models/isolation_forest")

DEFAULT_IF_PARAMS: dict[str, Any] = {
    # Number of trees — more is more stable; 200 balances speed and quality.
    "n_estimators": 200,
    # Subsample size per tree.  'auto' uses min(256, n_samples).
    # For large datasets an integer (e.g. 2048) saves memory.
    "max_samples": "auto",
    # Contamination: deliberately NOT set to the observed fraud rate.
    # 'auto' uses the sklearn default decision boundary (score_samples == 0).
    # Set explicitly only when you have a reliable prior on anomaly fraction.
    "contamination": "auto",
    # Proportion of features sampled per tree.
    "max_features": 1.0,
    # Use all cores.
    "n_jobs": -1,
    "random_state": 42,
    "verbose": 0,
}

# Score threshold: anomaly_score >= ANOMALY_THRESHOLD → is_anomaly = True.
# The default 0.0 is the model's natural decision boundary (score_samples == 0).
DEFAULT_SCORE_THRESHOLD = 0.0


# ---------------------------------------------------------------------------
# Split helper (reused from trainer; defined here for standalone use)
# ---------------------------------------------------------------------------

def make_if_splits(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    test_size: float = 0.10,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Simple stratified train / test split for Isolation Forest.

    Isolation Forest does NOT use a validation split for early stopping.
    The split is stratified to preserve the fraud proportion in test for
    fair evaluation.

    Parameters
    ----------
    X, y       : feature DataFrame, target Series
    test_size  : fraction held out for evaluation
    random_state : reproducibility seed

    Returns
    -------
    X_train, X_test, y_train, y_test
    """
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=test_size,
        random_state=random_state,
        stratify=y,
    )
    logger.info(
        "IF split — train: %d, test: %d (fraud rates: train %.3f%%, test %.3f%%)",
        len(X_train), len(X_test),
        y_train.mean() * 100, y_test.mean() * 100,
    )
    return X_train, X_test, y_train, y_test


# ---------------------------------------------------------------------------
# Score utilities
# ---------------------------------------------------------------------------

def raw_to_anomaly_score(raw_scores: np.ndarray) -> np.ndarray:
    """Convert IsolationForest.score_samples() output to anomaly scores.

    IsolationForest returns negative average path lengths; lower = more
    anomalous.  We negate so that higher = more anomalous, matching the
    directional convention used by the XGBoost fraud probability.

    Parameters
    ----------
    raw_scores : array of shape (n,) from IsolationForest.score_samples()

    Returns
    -------
    anomaly_scores : array of shape (n,) where higher = more anomalous
    """
    return -raw_scores


# ---------------------------------------------------------------------------
# Training entry point
# ---------------------------------------------------------------------------

def train_isolation_forest(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    params: dict[str, Any] | None = None,
    test_size: float = 0.10,
    model_dir: str | Path | None = None,
    random_state: int = 42,
    shared_preprocessor_path: str | Path | None = None,
) -> dict[str, Any]:
    """Train IsolationForest, save artifacts, return results for evaluation.

    Parameters
    ----------
    X          : full feature DataFrame (TransactionID and isFraud removed)
    y          : binary target Series (labels; NOT passed to model.fit())
    params     : override any key in DEFAULT_IF_PARAMS
    test_size  : fraction held for final evaluation
    model_dir  : root directory for IF artifacts (default: models/isolation_forest)
    random_state : reproducibility seed
    shared_preprocessor_path : path to an existing preprocessor.joblib (e.g.
        from the XGBoost run on the same split).  If provided, the preprocessor
        is loaded rather than re-fitted, which ensures identical feature
        transformation.  Only safe when X_train is the same split.

    Returns
    -------
    dict with keys:
        X_train, X_test, y_train, y_test   — raw DataFrames / Series
        X_train_t, X_test_t                — preprocessed numpy arrays
        model         : fitted IsolationForest
        pipeline      : fitted or loaded sklearn Pipeline
        feature_names : list[str]
        artifact_dir  : Path to saved artifacts
        train_anomaly_scores  : negated scores on training set
        test_anomaly_scores   : negated scores on test set
    """
    effective_params = {**DEFAULT_IF_PARAMS}
    if params:
        effective_params.update(params)

    # ------------------------------------------------------------------
    # 1. Split (train / test only; no validation split for IF)
    # ------------------------------------------------------------------
    X_train, X_test, y_train, y_test = make_if_splits(
        X, y, test_size=test_size, random_state=random_state
    )

    # ------------------------------------------------------------------
    # 2. Preprocessing — reuse shared artifact or fit fresh
    # ------------------------------------------------------------------
    if shared_preprocessor_path is not None:
        sp = Path(shared_preprocessor_path)
        if not sp.exists():
            raise FileNotFoundError(
                f"Shared preprocessor not found: {sp}\n"
                "Train XGBoost first or omit shared_preprocessor_path to fit a new one."
            )
        logger.info("Loading shared preprocessor from: %s", sp)
        pipeline = joblib.load(sp)
        feature_names = get_feature_names(pipeline, X_train)
        preprocessor_source = str(sp)
    else:
        logger.info("Fitting preprocessing pipeline on IF training data …")
        pipeline = build_preprocessing_pipeline(X_train)
        feature_names = get_feature_names(pipeline, X_train)
        preprocessor_source = "fitted_standalone"

    X_train_t = pipeline.transform(X_train)
    X_test_t = pipeline.transform(X_test)

    # ------------------------------------------------------------------
    # 3. Train IsolationForest — labels NOT passed to fit()
    # ------------------------------------------------------------------
    logger.info(
        "Training IsolationForest (%d estimators, contamination=%s) …",
        effective_params["n_estimators"],
        effective_params["contamination"],
    )
    model = IsolationForest(**effective_params)
    model.fit(X_train_t)   # ← Unsupervised: X only, no y
    logger.info("IsolationForest training complete.")

    # Compute anomaly scores (negated so higher = more anomalous)
    train_anomaly_scores = raw_to_anomaly_score(model.score_samples(X_train_t))
    test_anomaly_scores = raw_to_anomaly_score(model.score_samples(X_test_t))

    logger.info(
        "Train anomaly score stats — mean: %.4f, std: %.4f, min: %.4f, max: %.4f",
        train_anomaly_scores.mean(), train_anomaly_scores.std(),
        train_anomaly_scores.min(), train_anomaly_scores.max(),
    )

    # ------------------------------------------------------------------
    # 4. Save artifacts
    # ------------------------------------------------------------------
    artifact_dir = _save_if_artifacts(
        model=model,
        pipeline=pipeline,
        feature_names=feature_names,
        params=effective_params,
        preprocessor_source=preprocessor_source,
        data_stats={
            "n_train": len(y_train),
            "n_test": len(y_test),
            "n_features": len(feature_names),
            "fraud_rate_train": float(y_train.mean()),
            "fraud_rate_test": float(y_test.mean()),
        },
        model_dir=model_dir,
        shared=(shared_preprocessor_path is not None),
    )

    return {
        "X_train": X_train, "X_test": X_test,
        "y_train": y_train, "y_test": y_test,
        "X_train_t": X_train_t, "X_test_t": X_test_t,
        "model": model,
        "pipeline": pipeline,
        "feature_names": feature_names,
        "artifact_dir": artifact_dir,
        "train_anomaly_scores": train_anomaly_scores,
        "test_anomaly_scores": test_anomaly_scores,
    }


# ---------------------------------------------------------------------------
# Artifact persistence
# ---------------------------------------------------------------------------

def _save_if_artifacts(
    *,
    model: IsolationForest,
    pipeline: Any,
    feature_names: list[str],
    params: dict[str, Any],
    preprocessor_source: str,
    data_stats: dict[str, Any],
    model_dir: str | Path | None,
    shared: bool,
) -> Path:
    if model_dir is None:
        model_dir = DEFAULT_IF_MODEL_DIR
    artifact_dir = Path(model_dir) / f"v{IF_MODEL_VERSION}"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, artifact_dir / "if_model.joblib")
    joblib.dump(feature_names, artifact_dir / "feature_names.joblib")

    if not shared:
        # Save standalone preprocessor when not sharing from XGBoost run.
        joblib.dump(pipeline, artifact_dir / "preprocessor.joblib")

    metadata: dict[str, Any] = {
        "model_version": IF_MODEL_VERSION,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_type": "IsolationForest",
        "hyperparams": {
            k: (v if isinstance(v, (int, float, str, bool)) else str(v))
            for k, v in params.items()
        },
        "data_stats": data_stats,
        "preprocessor_source": preprocessor_source,
        "score_convention": (
            "anomaly_score = -IsolationForest.score_samples(). "
            "Higher anomaly_score → more anomalous. "
            "NOT a probability. Do NOT compare directly with XGBoost fraud_probability."
        ),
        "default_threshold": DEFAULT_SCORE_THRESHOLD,
        "threshold_note": (
            "Predictions use anomaly_score >= threshold. "
            "Default threshold=0.0 is the model's natural decision boundary. "
            "Adjust on held-out data for operational sensitivity requirements."
        ),
        "contamination_note": (
            "contamination='auto' was used. This does NOT assume the fraud rate "
            "equals the anomaly rate. Do not interpret the anomaly label as fraud."
        ),
        "shared_preprocessor": shared,
    }
    with open(artifact_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Isolation Forest artifacts saved to: %s", artifact_dir)
    return artifact_dir


# ---------------------------------------------------------------------------
# Artifact loading
# ---------------------------------------------------------------------------

def load_if_artifacts(
    model_dir: str | Path | None = None,
    version: str = IF_MODEL_VERSION,
    preprocessor_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load saved Isolation Forest artifacts for inference.

    Parameters
    ----------
    model_dir          : root directory for IF artifacts
    version            : artifact version string
    preprocessor_path  : explicit path to preprocessor.joblib.
        Required when the artifacts were saved with shared_preprocessor=True
        (i.e. the XGBoost preprocessor was reused).  If None and the standalone
        preprocessor.joblib exists in the artifact dir, it is loaded automatically.

    Returns
    -------
    dict with keys: model, pipeline, feature_names, metadata, artifact_dir
    """
    if model_dir is None:
        model_dir = DEFAULT_IF_MODEL_DIR
    artifact_dir = Path(model_dir) / f"v{version}"

    for fname in ["if_model.joblib", "feature_names.joblib", "metadata.json"]:
        p = artifact_dir / fname
        if not p.exists():
            raise FileNotFoundError(
                f"Artifact not found: {p}\n"
                "Run scripts/train_isolation_forest.py to generate artifacts first."
            )

    model = joblib.load(artifact_dir / "if_model.joblib")
    feature_names = joblib.load(artifact_dir / "feature_names.joblib")
    with open(artifact_dir / "metadata.json", encoding="utf-8") as f:
        metadata = json.load(f)

    # Resolve preprocessor
    standalone = artifact_dir / "preprocessor.joblib"
    if preprocessor_path is not None:
        pipeline = joblib.load(Path(preprocessor_path))
    elif standalone.exists():
        pipeline = joblib.load(standalone)
    else:
        raise FileNotFoundError(
            "No preprocessor found. Provide preprocessor_path= (e.g. path to "
            "XGBoost preprocessor.joblib) or retrain with shared_preprocessor_path=None."
        )

    logger.info("IF artifacts loaded from: %s", artifact_dir)
    return {
        "model": model,
        "pipeline": pipeline,
        "feature_names": feature_names,
        "metadata": metadata,
        "artifact_dir": artifact_dir,
    }
