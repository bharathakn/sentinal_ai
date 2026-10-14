"""
Sentinel AI — Isolation Forest anomaly predictor.

Loads saved IF artifacts and provides inference for the Sentinel AI pipeline.

Score convention
----------------
``anomaly_score``: Higher = more anomalous. NOT a fraud probability.

The IF anomaly score and the XGBoost ``fraud_probability`` have different
meanings and scales.  They must NOT be treated as interchangeable or directly
combined unless a tested fusion strategy exists.

Usage
-----
    from src.ml.if_predictor import AnomalyPredictor

    predictor = AnomalyPredictor()           # loads artifacts once
    scores = predictor.score(X_df)           # array of anomaly scores
    results = predictor.predict(X_df)        # (scores, is_anomaly array)
    detail = predictor.score_transaction(tx) # dict for pipeline use
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from .if_trainer import (
    load_if_artifacts,
    raw_to_anomaly_score,
    DEFAULT_SCORE_THRESHOLD,
)

logger = logging.getLogger(__name__)


class AnomalyPredictor:
    """Inference wrapper for the saved IsolationForest model.

    Parameters
    ----------
    model_dir          : path to the root IF model directory
    version            : artifact version string
    preprocessor_path  : explicit preprocessor.joblib path (required when the
        standalone preprocessor was not saved, e.g. when sharing XGBoost's)
    """

    def __init__(
        self,
        model_dir: str | None = None,
        version: str | None = None,
        preprocessor_path: str | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {}
        if model_dir is not None:
            kwargs["model_dir"] = model_dir
        if version is not None:
            kwargs["version"] = version
        if preprocessor_path is not None:
            kwargs["preprocessor_path"] = preprocessor_path

        artifacts = load_if_artifacts(**kwargs)
        self._model = artifacts["model"]
        self._pipeline = artifacts["pipeline"]
        self._feature_names = artifacts["feature_names"]
        self._metadata = artifacts["metadata"]
        self._default_threshold: float = float(
            self._metadata.get("default_threshold", DEFAULT_SCORE_THRESHOLD)
        )
        logger.info(
            "AnomalyPredictor initialised (IF version %s, threshold=%.2f).",
            self._metadata.get("model_version"),
            self._default_threshold,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(self, X: pd.DataFrame) -> np.ndarray:
        """Return anomaly scores for each row of *X*.

        Scores are negated IsolationForest.score_samples() values:
        **higher score → more anomalous**.

        Parameters
        ----------
        X : pd.DataFrame with IEEE-CIS feature columns (no TransactionID/isFraud)

        Returns
        -------
        np.ndarray of shape (n_samples,), dtype float64
        """
        X_t = self._pipeline.transform(X)
        raw = self._model.score_samples(X_t)
        return raw_to_anomaly_score(raw)

    def predict(
        self,
        X: pd.DataFrame,
        *,
        threshold: float | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return (anomaly_scores, is_anomaly) for each row.

        Parameters
        ----------
        X         : feature DataFrame
        threshold : score threshold; scores >= threshold → anomaly.
                    Defaults to value in saved metadata.

        Returns
        -------
        anomaly_scores : np.ndarray of float
        is_anomaly     : np.ndarray of bool
        """
        thr = threshold if threshold is not None else self._default_threshold
        scores = self.score(X)
        is_anomaly = scores >= thr
        return scores, is_anomaly

    def score_transaction(
        self,
        transaction: dict[str, Any],
        *,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        """Score a single transaction dict and return a structured result.

        This is the primary entry point for Sentinel AI Agent 1 integration.

        Parameters
        ----------
        transaction : dict with IEEE-CIS feature keys.  Unknown keys are ignored;
                      missing keys become NaN and are handled by the imputer.
        threshold   : override the default decision threshold.

        Returns
        -------
        dict with:
            anomaly_score   : float  (higher = more anomalous)
            is_anomaly      : bool
            threshold_used  : float
            model_version   : str
            score_note      : str  (interpretation disclaimer)
        """
        df = pd.DataFrame([transaction])
        # Strip leakage columns if caller accidentally included them.
        for col in ("TransactionID", "isFraud"):
            if col in df.columns:
                df = df.drop(columns=[col])

        # Reindex to all expected feature columns; missing → NaN → imputer.
        df = df.reindex(columns=self._feature_names)

        scores, _ = self.predict(df, threshold=threshold)
        thr = threshold if threshold is not None else self._default_threshold

        return {
            "anomaly_score": round(float(scores[0]), 6),
            "is_anomaly": bool(scores[0] >= thr),
            "threshold_used": thr,
            "model_version": self._metadata.get("model_version"),
            "score_note": (
                "Anomaly score from an unsupervised IsolationForest model. "
                "Higher scores indicate greater statistical unusualness. "
                "This is NOT a fraud probability and should not be compared "
                "directly with XGBoost fraud_probability."
            ),
        }

    @property
    def feature_names(self) -> list[str]:
        return self._feature_names

    @property
    def metadata(self) -> dict[str, Any]:
        return self._metadata
