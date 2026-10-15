"""
Sentinel AI — Agent 1 (Anomaly Detector) ML scoring integration.

Purpose
-------
Provide the ML scoring entry point for Agent 1 of the Sentinel AI investigation
pipeline.  Agent 1 uses both the XGBoost supervised fraud detector and the
Isolation Forest unsupervised anomaly detector to produce a structured signal
that downstream agents can use during investigation.

Integration status
------------------
* The LangGraph graph and agent node wiring exist on a separate branch and
  have not yet been merged. This module implements the ML inference side of
  Agent 1 so it can be integrated when the graph is ready.
* This module does NOT import LangGraph. It is a pure Python inference layer
  that returns a structured dict, which Agent 1 can consume and add to its
  state without coupling to the graph framework.

Design rules
------------
* Models are loaded ONCE at construction time and reused. Never retrain on startup.
* XGBoost output (fraud_probability) and Isolation Forest output (anomaly_score)
  are kept in SEPARATE keys. They must NOT be summed or directly compared without
  a tested fusion strategy.
* Each result carries the model version and threshold used.
* CanonicalTransaction is mapped to features through feature_mapper.py.
  Most features will be NaN-imputed. See feature_mapper.describe_mapping().
* Missing artifact files produce a clear, actionable error message.
* This module is safe to import without the full IEEE-CIS dataset present.

Usage (from Agent 1 node)
--------------------------
    from src.ml.agent1_scorer import Agent1Scorer

    scorer = Agent1Scorer()               # load once
    signal = scorer.score(canonical_tx)   # call per transaction

    # signal["xgboost"]["fraud_probability"]   — XGBoost fraud probability
    # signal["iforest"]["anomaly_score"]        — IF anomaly score (NOT a probability)
    # signal["combined_note"]                  — explicit disclaimer
"""

from __future__ import annotations

import logging
from typing import Any

from .feature_mapper import canonical_to_xgb_features, canonical_to_if_features, describe_mapping

logger = logging.getLogger(__name__)


class Agent1Scorer:
    """Loads and caches both ML models for Agent 1 scoring.

    Parameters
    ----------
    xgb_model_dir : path to XGBoost artifact directory root
    xgb_version   : XGBoost artifact version string
    if_model_dir  : path to IF artifact directory root
    if_version    : IF artifact version string
    if_preprocessor_path : path to IF preprocessor.joblib (required when standalone)
    xgb_threshold : override the saved XGBoost classification threshold
    if_threshold  : override the saved IF anomaly score threshold
    """

    def __init__(
        self,
        xgb_model_dir: str | None = None,
        xgb_version: str | None = None,
        if_model_dir: str | None = None,
        if_version: str | None = None,
        if_preprocessor_path: str | None = None,
        xgb_threshold: float | None = None,
        if_threshold: float | None = None,
    ) -> None:
        # Lazy import to avoid requiring both models to be trained just to import
        # this module. Each predictor raises FileNotFoundError with a clear message
        # if artifacts are missing.
        from .predictor import FraudPredictor
        from .if_predictor import AnomalyPredictor

        xgb_kwargs: dict[str, Any] = {}
        if xgb_model_dir is not None:
            xgb_kwargs["model_dir"] = xgb_model_dir
        if xgb_version is not None:
            xgb_kwargs["version"] = xgb_version
        self._xgb = FraudPredictor(**xgb_kwargs)
        self._xgb_threshold = xgb_threshold  # None → uses saved default

        if_kwargs: dict[str, Any] = {}
        if if_model_dir is not None:
            if_kwargs["model_dir"] = if_model_dir
        if if_version is not None:
            if_kwargs["version"] = if_version
        if if_preprocessor_path is not None:
            if_kwargs["preprocessor_path"] = if_preprocessor_path
        self._iforest = AnomalyPredictor(**if_kwargs)
        self._if_threshold = if_threshold  # None → uses saved default

        logger.info(
            "Agent1Scorer ready. XGBoost version=%s, IF version=%s.",
            self._xgb.metadata.get("model_version"),
            self._iforest.metadata.get("model_version"),
        )

    def score(self, transaction: Any) -> dict[str, Any]:
        """Score a CanonicalTransaction with both models.

        Parameters
        ----------
        transaction : CanonicalTransaction instance (or any object accepted
            by canonical_to_xgb_features).

        Returns
        -------
        dict with structure:
            {
              "raw_record_id"  : str          — from transaction.raw_record_id
              "source_dataset" : str          — from transaction.source_dataset
              "xgboost": {
                  "fraud_probability"   : float  — [0, 1] supervised probability
                  "is_fraud_predicted"  : bool
                  "threshold_used"      : float
                  "model_version"       : str
                  "note"                : str    — interpretation disclaimer
              },
              "iforest": {
                  "anomaly_score"       : float  — NOT a probability; higher = more unusual
                  "is_anomaly"          : bool
                  "threshold_used"      : float
                  "model_version"       : str
                  "score_note"          : str    — interpretation disclaimer
              },
              "combined_note" : str  — explicit warning against combining scores
            }
        """
        # Extract features (most will be NaN-imputed)
        xgb_features = canonical_to_xgb_features(transaction)
        if_features = canonical_to_if_features(transaction)

        # --- XGBoost ---
        xgb_result = self._xgb.predict_transaction(
            xgb_features, threshold=self._xgb_threshold
        )

        # --- Isolation Forest ---
        if_result = self._iforest.score_transaction(
            if_features, threshold=self._if_threshold
        )

        # Provenance
        raw_id = getattr(transaction, "raw_record_id", None)
        source = getattr(transaction, "source_dataset", None)

        return {
            "raw_record_id": str(raw_id) if raw_id is not None else None,
            "source_dataset": str(source) if source is not None else None,
            "xgboost": xgb_result,
            "iforest": if_result,
            "combined_note": (
                "XGBoost fraud_probability and Isolation Forest anomaly_score are "
                "independent signals with different scales and meanings. "
                "Do NOT sum or directly compare them. "
                "Both are statistical signals, not proof of fraud."
            ),
            "mapping_summary": {
                "n_features_mapped": len(xgb_features),
                "mapping_warning": (
                    "Only a small subset of IEEE-CIS features are available from "
                    "CanonicalTransaction. Most features will be NaN-imputed. "
                    "Model accuracy is lower than reported IEEE-CIS benchmarks."
                ),
            },
        }

    def score_raw(self, features: dict[str, Any]) -> dict[str, Any]:
        """Score a raw IEEE-CIS feature dict (bypasses feature mapping).

        Use this when the caller has already prepared the full feature dict,
        e.g. when scoring directly from the IEEE-CIS dataset during evaluation.

        Parameters
        ----------
        features : dict with IEEE-CIS feature keys (no TransactionID/isFraud).

        Returns
        -------
        Same structure as score(), but without provenance fields.
        """
        xgb_result = self._xgb.predict_transaction(features, threshold=self._xgb_threshold)
        if_result = self._iforest.score_transaction(features, threshold=self._if_threshold)
        return {
            "raw_record_id": None,
            "source_dataset": None,
            "xgboost": xgb_result,
            "iforest": if_result,
            "combined_note": (
                "XGBoost fraud_probability and Isolation Forest anomaly_score are "
                "independent signals. Do NOT sum them. Neither is proof of fraud."
            ),
        }

    @property
    def mapping_info(self) -> dict[str, Any]:
        """Return a description of the CanonicalTransaction field mapping."""
        return describe_mapping()
