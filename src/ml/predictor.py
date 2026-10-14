"""
Sentinel AI — Inference predictor.

Loads saved artifacts (preprocessor + model) and provides a prediction
interface that can be called on:

1. Raw pandas DataFrames (matching the IEEE-CIS column schema).
2. Dicts representing individual transactions (for Sentinel AI pipeline use).

The predictor never retrains. If artifacts are missing, it raises a clear
error directing the operator to run the training script.

Classification threshold
------------------------
Default threshold is 0.5 (documented in metadata.json).
A custom threshold can be passed at call time.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from .trainer import load_artifacts

logger = logging.getLogger(__name__)


class FraudPredictor:
    """Inference wrapper around saved XGBoost artifacts.

    Parameters
    ----------
    model_dir : path to the root model directory (e.g. ``models/xgboost``)
    version   : artifact version string (default: same as trainer.MODEL_VERSION)
    """

    def __init__(
        self,
        model_dir: str | None = None,
        version: str | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {}
        if model_dir is not None:
            kwargs["model_dir"] = model_dir
        if version is not None:
            kwargs["version"] = version

        artifacts = load_artifacts(**kwargs)
        self._model = artifacts["model"]
        self._pipeline = artifacts["pipeline"]
        self._feature_names = artifacts["feature_names"]
        self._metadata = artifacts["metadata"]
        self._default_threshold: float = self._metadata.get("classification_threshold", 0.5)
        logger.info(
            "FraudPredictor initialised from artifacts (version %s, threshold=%.2f).",
            self._metadata.get("model_version"),
            self._default_threshold,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Return fraud probability scores for each row in *X*.

        Parameters
        ----------
        X : pd.DataFrame
            Feature matrix in the IEEE-CIS schema (TransactionID and isFraud
            must already be removed by the caller).

        Returns
        -------
        np.ndarray of shape (n_samples,) with fraud probabilities in [0, 1].
        """
        X_t = self._pipeline.transform(X)
        probas = self._model.predict_proba(X_t)[:, 1]
        return probas

    def predict(
        self,
        X: pd.DataFrame,
        *,
        threshold: float | None = None,
    ) -> np.ndarray:
        """Return binary fraud predictions (0/1).

        Parameters
        ----------
        X         : feature DataFrame
        threshold : classification threshold; defaults to value in metadata.

        Returns
        -------
        np.ndarray of int (0 or 1).
        """
        thr = threshold if threshold is not None else self._default_threshold
        probas = self.predict_proba(X)
        return (probas >= thr).astype(int)

    def predict_transaction(
        self,
        transaction: dict[str, Any],
        *,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        """Score a single transaction dict and return a structured result.

        This is the entry point intended for the Sentinel AI investigation
        pipeline (Agent 1 — Anomaly Detector).

        Parameters
        ----------
        transaction : dict with IEEE-CIS feature keys.  Unknown keys are
            ignored; missing keys default to NaN via pd.DataFrame.

        Returns
        -------
        dict with:
            fraud_probability : float
            is_fraud_predicted : bool
            threshold_used     : float
            model_version      : str
            note               : str (disclaimer)
        """
        df = pd.DataFrame([transaction])
        # Drop leakage columns if caller accidentally included them.
        for col in ("TransactionID", "isFraud"):
            if col in df.columns:
                df = df.drop(columns=[col])

        # Reindex to include all expected feature columns; missing ones become NaN
        # so the fitted imputers can handle them correctly.
        df = df.reindex(columns=self._feature_names)

        proba = float(self.predict_proba(df)[0])
        thr = threshold if threshold is not None else self._default_threshold

        return {
            "fraud_probability": round(proba, 6),
            "is_fraud_predicted": proba >= thr,
            "threshold_used": thr,
            "model_version": self._metadata.get("model_version"),
            "note": (
                "This score is a statistical anomaly signal from a supervised ML model. "
                "It is not proof of fraud and must be interpreted alongside investigative evidence."
            ),
        }

    @property
    def feature_names(self) -> list[str]:
        return self._feature_names

    @property
    def metadata(self) -> dict[str, Any]:
        return self._metadata
