"""
Sentinel AI — XGBoost trainer.

Responsibility
--------------
Train, validate, and persist the XGBoost binary classifier for fraud detection.

Design
------
* Hyperparameters are configurable via a plain dict; defaults are provided.
* Class imbalance is handled via ``scale_pos_weight`` (ratio of negatives to
  positives in the *training* split), not by resampling.
* Model selection uses an evaluation set (validation split); the held-out test
  set is never seen during training.
* The fitted preprocessing pipeline and model are saved together as a
  versioned directory of joblib artifacts.
* Training is separate from inference; never retrain at application startup.

Artifact layout
---------------
``models/xgboost/v<VERSION>/``
    preprocessor.joblib   — fitted sklearn Pipeline
    xgb_model.joblib      — fitted XGBClassifier
    feature_names.joblib  — ordered list of feature names
    metadata.json         — version, timestamp, hyperparams, data stats
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from .preprocessor import build_preprocessing_pipeline, get_feature_names

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL_VERSION = "1"
DEFAULT_MODEL_DIR = Path("models/xgboost")

DEFAULT_HYPERPARAMS: dict[str, Any] = {
    # Objective
    "objective": "binary:logistic",
    "eval_metric": "aucpr",  # PR-AUC; best for imbalanced fraud data
    # Capacity / regularisation
    "n_estimators": 500,
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "gamma": 1,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    # Resources
    "n_jobs": -1,
    "tree_method": "hist",          # CPU-friendly histogram method
    "random_state": 42,
    # Early stopping
    "early_stopping_rounds": 30,
}


# ---------------------------------------------------------------------------
# Split helper
# ---------------------------------------------------------------------------


def make_splits(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    val_size: float = 0.10,
    test_size: float = 0.10,
    random_state: int = 42,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.Series,
    pd.Series,
    pd.Series,
]:
    """Leakage-safe stratified train / validation / test split.

    Stratification preserves the fraud class ratio in every split.

    Parameters
    ----------
    X : feature DataFrame
    y : target Series (0/1)
    val_size  : fraction of total data used for validation
    test_size : fraction of total data used for final held-out test
    random_state : reproducibility seed

    Returns
    -------
    X_train, X_val, X_test, y_train, y_val, y_test
    """
    # 1. Carve out test set first so it is never touched during training.
    X_temp, X_test, y_temp, y_test = train_test_split(
        X, y,
        test_size=test_size,
        random_state=random_state,
        stratify=y,
    )

    # 2. From the remainder, carve out validation.
    relative_val = val_size / (1.0 - test_size)
    X_train, X_val, y_train, y_val = train_test_split(
        X_temp, y_temp,
        test_size=relative_val,
        random_state=random_state,
        stratify=y_temp,
    )

    logger.info(
        "Split sizes — train: %d, val: %d, test: %d", len(X_train), len(X_val), len(X_test)
    )
    logger.info(
        "Fraud rates  — train: %.3f%%, val: %.3f%%, test: %.3f%%",
        y_train.mean() * 100,
        y_val.mean() * 100,
        y_test.mean() * 100,
    )
    return X_train, X_val, X_test, y_train, y_val, y_test


# ---------------------------------------------------------------------------
# Training entry point
# ---------------------------------------------------------------------------


def train(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    hyperparams: dict[str, Any] | None = None,
    val_size: float = 0.10,
    test_size: float = 0.10,
    model_dir: str | Path | None = None,
    random_state: int = 42,
) -> dict[str, Any]:
    """Train XGBoost, save artifacts, return split datasets for evaluation.

    Parameters
    ----------
    X           : full feature DataFrame (leakage columns already removed)
    y           : binary target Series
    hyperparams : override any key in DEFAULT_HYPERPARAMS
    val_size    : fraction of data held for validation (early stopping)
    test_size   : fraction of data held for final evaluation
    model_dir   : root directory for saved artifacts (default: models/xgboost)
    random_state: reproducibility seed

    Returns
    -------
    dict with keys:
        X_train, X_val, X_test, y_train, y_val, y_test  — raw DataFrames/Series
        X_train_t, X_val_t, X_test_t                    — preprocessed arrays
        model    : fitted XGBClassifier
        pipeline : fitted sklearn Pipeline
        feature_names : list[str]
        artifact_dir  : Path where artifacts were saved
    """
    hparams = {**DEFAULT_HYPERPARAMS}
    if hyperparams:
        hparams.update(hyperparams)

    # ------------------------------------------------------------------
    # 1. Split
    # ------------------------------------------------------------------
    X_train, X_val, X_test, y_train, y_val, y_test = make_splits(
        X, y,
        val_size=val_size,
        test_size=test_size,
        random_state=random_state,
    )

    # ------------------------------------------------------------------
    # 2. Preprocessing — fit on training split only
    # ------------------------------------------------------------------
    logger.info("Fitting preprocessing pipeline on training data …")
    pipeline = build_preprocessing_pipeline(X_train)
    feature_names = get_feature_names(pipeline, X_train)

    X_train_t = pipeline.transform(X_train)
    X_val_t = pipeline.transform(X_val)
    X_test_t = pipeline.transform(X_test)

    # ------------------------------------------------------------------
    # 3. Class-imbalance weight
    # ------------------------------------------------------------------
    n_neg = int((y_train == 0).sum())
    n_pos = int((y_train == 1).sum())
    scale_pos_weight = n_neg / n_pos if n_pos > 0 else 1.0
    logger.info(
        "Class imbalance — neg: %d, pos: %d, scale_pos_weight: %.2f",
        n_neg, n_pos, scale_pos_weight,
    )

    # Extract early_stopping_rounds (XGBoost 3.x: constructor param, not fit() param)
    early_stopping_rounds = hparams.pop("early_stopping_rounds", 30)

    # ------------------------------------------------------------------
    # 4. Train XGBoost
    # ------------------------------------------------------------------
    logger.info("Training XGBClassifier …")
    model = XGBClassifier(
        **hparams,
        scale_pos_weight=scale_pos_weight,
        enable_categorical=False,
        early_stopping_rounds=early_stopping_rounds,
    )

    model.fit(
        X_train_t,
        y_train,
        eval_set=[(X_val_t, y_val)],
        verbose=50,
    )
    logger.info("Training complete. Best iteration: %d", model.best_iteration)

    # ------------------------------------------------------------------
    # 5. Save artifacts
    # ------------------------------------------------------------------
    artifact_dir = _save_artifacts(
        model=model,
        pipeline=pipeline,
        feature_names=feature_names,
        hparams={**hparams, "early_stopping_rounds": early_stopping_rounds,
                 "scale_pos_weight": scale_pos_weight},
        data_stats={
            "n_train": len(y_train),
            "n_val": len(y_val),
            "n_test": len(y_test),
            "n_features": len(feature_names),
            "fraud_rate_train": float(y_train.mean()),
            "fraud_rate_val": float(y_val.mean()),
            "fraud_rate_test": float(y_test.mean()),
        },
        model_dir=model_dir,
    )

    return {
        "X_train": X_train, "X_val": X_val, "X_test": X_test,
        "y_train": y_train, "y_val": y_val, "y_test": y_test,
        "X_train_t": X_train_t, "X_val_t": X_val_t, "X_test_t": X_test_t,
        "model": model,
        "pipeline": pipeline,
        "feature_names": feature_names,
        "artifact_dir": artifact_dir,
    }


# ---------------------------------------------------------------------------
# Artifact persistence
# ---------------------------------------------------------------------------


def _save_artifacts(
    *,
    model: XGBClassifier,
    pipeline: Any,
    feature_names: list[str],
    hparams: dict[str, Any],
    data_stats: dict[str, Any],
    model_dir: str | Path | None,
) -> Path:
    """Persist preprocessor, model, feature names, and metadata."""
    if model_dir is None:
        model_dir = DEFAULT_MODEL_DIR
    artifact_dir = Path(model_dir) / f"v{MODEL_VERSION}"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(pipeline, artifact_dir / "preprocessor.joblib")
    joblib.dump(model, artifact_dir / "xgb_model.joblib")
    joblib.dump(feature_names, artifact_dir / "feature_names.joblib")

    metadata = {
        "model_version": MODEL_VERSION,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "xgboost_best_iteration": int(model.best_iteration),
        "hyperparams": {
            k: (v if isinstance(v, (int, float, str, bool)) else str(v))
            for k, v in hparams.items()
        },
        "data_stats": data_stats,
        "classification_threshold": 0.5,
        "threshold_note": (
            "Default 0.5 threshold applied. Adjust threshold on validation data "
            "to trade precision vs. recall for operational requirements."
        ),
    }
    with open(artifact_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Artifacts saved to: %s", artifact_dir)
    return artifact_dir


# ---------------------------------------------------------------------------
# Artifact loading
# ---------------------------------------------------------------------------


def load_artifacts(
    model_dir: str | Path | None = None,
    version: str = MODEL_VERSION,
) -> dict[str, Any]:
    """Load persisted artifacts for inference.

    Returns
    -------
    dict with keys: model, pipeline, feature_names, metadata
    """
    if model_dir is None:
        model_dir = DEFAULT_MODEL_DIR
    artifact_dir = Path(model_dir) / f"v{version}"

    required = ["preprocessor.joblib", "xgb_model.joblib", "feature_names.joblib", "metadata.json"]
    for fname in required:
        p = artifact_dir / fname
        if not p.exists():
            raise FileNotFoundError(
                f"Artifact not found: {p}\n"
                "Run train_pipeline.py to generate artifacts first."
            )

    pipeline = joblib.load(artifact_dir / "preprocessor.joblib")
    model = joblib.load(artifact_dir / "xgb_model.joblib")
    feature_names = joblib.load(artifact_dir / "feature_names.joblib")
    with open(artifact_dir / "metadata.json", encoding="utf-8") as f:
        metadata = json.load(f)

    logger.info("Artifacts loaded from: %s", artifact_dir)
    return {
        "model": model,
        "pipeline": pipeline,
        "feature_names": feature_names,
        "metadata": metadata,
        "artifact_dir": artifact_dir,
    }
