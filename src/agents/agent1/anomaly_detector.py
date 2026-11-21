"""
Sentinel AI — Agent 1: Anomaly Detector.

Responsibility
--------------
Implement the complete Agent 1 investigation node:

  CanonicalTransaction / raw features
    → input validation
    → feature extraction (via feature_mapper)
    → XGBoost fraud scoring
    → SHAP feature explanations
    → Isolation Forest anomaly scoring
    → combined_confidence calculation
    → structured Agent1Output

This module is the callable entry point for Agent 1. It is designed to be
used standalone (for unit testing and direct invocation) and as a LangGraph
node once LangGraph is added to the project stack.

Design rules
------------
* Models are loaded ONCE at construction time (lazy by default).
* combined_confidence is a documented heuristic — NOT a calibrated probability.
  See output_schema.COMBINED_CONFIDENCE_NOTE for the full definition.
* SHAP is computed per-prediction using the cached TreeExplainer.
  This adds latency but provides per-prediction attributions.
* A missing model is a hard error for that model's score; combined_confidence
  becomes None when either model is unavailable.
* Never fabricate scores. All None fields mean "genuinely unavailable".
* LangGraph integration: expose run_on_state() classmethod when LangGraph
  is available. The node consumes SentinelState["transaction"] and writes
  back to SentinelState["agent1_output"].

Combined confidence strategy
-----------------------------
XGBoost fraud_probability ∈ [0, 1] is already a well-defined probability-like
score. Isolation Forest anomaly_score has a different scale (raw negated
score_samples, typically in roughly (-0.5, 0.5) on this dataset).

To produce a meaningful composite:
  1. XGBoost component: fraud_probability directly (weight = 0.70).
  2. IF component: sigmoid-normalised anomaly_score relative to the calibrated
     IF threshold (0.4679). Normalisation uses a logistic function centred on
     the calibrated threshold with a scale factor derived from the threshold
     value itself. This maps the IF score to [0, 1] in a monotone way.
     (weight = 0.30).

  combined_confidence = 0.70 * xgb_prob + 0.30 * sigmoid_if

Weights reflect relative model precision (XGBoost PR-AUC=0.662 vs IF
PR-AUC=0.178). Weights are configurable. No test-set fitting is performed.

combined_confidence is None when either model score is unavailable.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import ValidationError

from ...schemas.canonical_transaction import CanonicalTransaction
from ...ml.feature_mapper import canonical_to_xgb_features, canonical_to_if_features, describe_mapping
from ...ml.predictor import FraudPredictor
from ...ml.if_predictor import AnomalyPredictor
from ...ml.explainer import explain_prediction

from .output_schema import (
    Agent1Output,
    AgentStatus,
    ScoringMode,
    DeviationFeature,
    XGBoostDetail,
    IsolationForestDetail,
    FeatureMappingInfo,
    COMBINED_CONFIDENCE_NOTE,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Combined confidence constants
# ---------------------------------------------------------------------------

# Calibrated IF threshold (from models/isolation_forest/v1/threshold_calibration.json)
# Used as the sigmoid centre for IF score normalisation.
_DEFAULT_IF_CALIBRATED_THRESHOLD: float = 0.4679

# Sigmoid scale: controls how sharply the IF score maps around the threshold.
# Larger k → steeper transition. k=5 gives a smooth [0,1] mapping.
_IF_SIGMOID_SCALE: float = 5.0

# Combination weights (XGBoost, IF). Must sum to 1.0.
_DEFAULT_XGB_WEIGHT: float = 0.70
_DEFAULT_IF_WEIGHT: float = 0.30


def _sigmoid_normalise_if_score(
    anomaly_score: float,
    threshold: float = _DEFAULT_IF_CALIBRATED_THRESHOLD,
    scale: float = _IF_SIGMOID_SCALE,
) -> float:
    """Map an IF anomaly_score to [0, 1] via a sigmoid centred on threshold.

    Scores at the threshold → 0.5.
    Scores well above threshold → approach 1.0 (highly anomalous).
    Scores well below threshold → approach 0.0 (normal).

    Parameters
    ----------
    anomaly_score : IF anomaly_score (higher = more anomalous)
    threshold     : calibrated IF threshold from validation data
    scale         : sigmoid steepness

    Returns
    -------
    float in [0, 1]
    """
    x = scale * (anomaly_score - threshold)
    return 1.0 / (1.0 + math.exp(-x))


def _compute_combined_confidence(
    xgb_prob: float,
    if_anomaly_score: float,
    xgb_weight: float = _DEFAULT_XGB_WEIGHT,
    if_weight: float = _DEFAULT_IF_WEIGHT,
    if_threshold: float = _DEFAULT_IF_CALIBRATED_THRESHOLD,
) -> float:
    """Compute combined_confidence from XGBoost probability and IF anomaly score.

    See module docstring for the full strategy definition.

    Parameters
    ----------
    xgb_prob        : XGBoost fraud_probability ∈ [0, 1]
    if_anomaly_score: IF anomaly_score (higher = more anomalous)
    xgb_weight      : weight for XGBoost component (default 0.70)
    if_weight       : weight for IF component (default 0.30)
    if_threshold    : calibrated IF threshold used as sigmoid centre

    Returns
    -------
    float ∈ [0.0, 1.0]
    """
    if_normalised = _sigmoid_normalise_if_score(if_anomaly_score, threshold=if_threshold)
    combined = xgb_weight * xgb_prob + if_weight * if_normalised
    # Clamp to [0,1] for robustness against floating point edge cases.
    return float(max(0.0, min(1.0, combined)))


# ---------------------------------------------------------------------------
# Agent 1 implementation
# ---------------------------------------------------------------------------


class AnomalyDetectorAgent:
    """Agent 1 — Anomaly Detector.

    Loads both ML models at construction time and provides a score() method
    for investigating individual transactions.

    Parameters
    ----------
    xgb_model_dir : path to XGBoost artifact directory root
    xgb_version   : XGBoost artifact version string
    if_model_dir  : path to IF artifact directory root
    if_version    : IF artifact version string
    if_preprocessor_path : explicit path to IF preprocessor.joblib (if standalone)
    xgb_threshold : override the saved XGBoost classification threshold
    if_threshold  : override the saved IF classification threshold
    xgb_weight    : combined_confidence weight for XGBoost (default 0.70)
    if_weight     : combined_confidence weight for IF (default 0.30)
    top_n_shap    : number of top SHAP features to return (default 10)
    """

    def __init__(
        self,
        xgb_model_dir: Optional[str] = None,
        xgb_version: Optional[str] = None,
        if_model_dir: Optional[str] = None,
        if_version: Optional[str] = None,
        if_preprocessor_path: Optional[str] = None,
        xgb_threshold: Optional[float] = None,
        if_threshold: Optional[float] = None,
        xgb_weight: float = _DEFAULT_XGB_WEIGHT,
        if_weight: float = _DEFAULT_IF_WEIGHT,
        top_n_shap: int = 10,
        india_model_dir: Optional[str] = None,
        use_india_model: bool = True,
    ) -> None:
        # Validate weights
        if not math.isclose(xgb_weight + if_weight, 1.0, rel_tol=1e-6):
            raise ValueError(
                f"xgb_weight + if_weight must equal 1.0, got {xgb_weight + if_weight}"
            )

        self._xgb_weight = xgb_weight
        self._if_weight = if_weight
        self._top_n_shap = top_n_shap

        # --- Load XGBoost predictor ---
        # FileNotFoundError propagates to the caller: a missing artifact is a
        # configuration error, not a recoverable runtime failure.
        self._xgb_predictor: Any = None
        self._xgb_load_error: Optional[str] = None
        xgb_init_kwargs: dict[str, Any] = {}
        if xgb_model_dir is not None:
            xgb_init_kwargs["model_dir"] = xgb_model_dir
        if xgb_version is not None:
            xgb_init_kwargs["version"] = xgb_version
        # Raises FileNotFoundError with a clear message if artifacts are missing.
        self._xgb_predictor = FraudPredictor(**xgb_init_kwargs)
        self._xgb_threshold = xgb_threshold  # None → uses saved default
        logger.info(
            "AnomalyDetectorAgent: XGBoost loaded (version=%s).",
            self._xgb_predictor.metadata.get("model_version"),
        )

        # --- Load Isolation Forest predictor ---
        # Same fail-fast policy as XGBoost: FileNotFoundError propagates.
        self._if_predictor: Any = None
        self._if_load_error: Optional[str] = None
        if_init_kwargs: dict[str, Any] = {}
        if if_model_dir is not None:
            if_init_kwargs["model_dir"] = if_model_dir
        if if_version is not None:
            if_init_kwargs["version"] = if_version
        if if_preprocessor_path is not None:
            if_init_kwargs["preprocessor_path"] = if_preprocessor_path
        # Raises FileNotFoundError with a clear message if artifacts are missing.
        self._if_predictor = AnomalyPredictor(**if_init_kwargs)
        self._if_threshold = if_threshold  # None → uses saved default
        logger.info(
            "AnomalyDetectorAgent: Isolation Forest loaded (version=%s).",
            self._if_predictor.metadata.get("model_version"),
        )

        # --- Optional India-native behavioural model (Phase 9.5) ---
        # Missing artifacts are NOT fatal: India transactions then fall back
        # to the IEEE-CIS canonical-mapped path with a coverage warning.
        self._india_scorer: Any = None
        self._india_load_error: Optional[str] = None
        if use_india_model:
            try:
                from ...ml.india_behaviour_model import DEFAULT_MODEL_DIR, IndiaBehaviourScorer
                self._india_scorer = IndiaBehaviourScorer(
                    india_model_dir if india_model_dir is not None else DEFAULT_MODEL_DIR
                )
            except Exception as exc:  # noqa: BLE001
                self._india_load_error = f"{type(exc).__name__}: {exc}"
                logger.info("India behaviour model not loaded: %s", self._india_load_error)

        logger.info(
            "AnomalyDetectorAgent initialised. XGBoost version=%s, IF version=%s.",
            self._xgb_predictor.metadata.get("model_version"),
            self._if_predictor.metadata.get("model_version"),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(
        self,
        transaction: CanonicalTransaction,
    ) -> Agent1Output:
        """Score a CanonicalTransaction with both ML models.

        This is the primary entry point for Agent 1. It executes the full
        investigation flow and returns a structured, validated Agent1Output.

        Parameters
        ----------
        transaction : CanonicalTransaction instance (validated Pydantic model)

        Returns
        -------
        Agent1Output — always returns a structured result, never raises for
            model inference errors. Validation errors are reflected in status.
        """
        scored_at = datetime.now(timezone.utc)
        warnings: list[str] = []
        errors: list[str] = []

        # --- Extract provenance ---
        tx_id = str(transaction.raw_record_id) if transaction.raw_record_id else None
        source_ds = str(getattr(transaction.source_dataset, "value", transaction.source_dataset)) \
            if transaction.source_dataset else None

        # --- Route India transactions to the India-native model ---
        if source_ds == "INDIA_SYNTHETIC":
            if self._india_scorer is not None:
                return self._score_india(transaction, tx_id, source_ds, scored_at)
            warnings.append(
                "India behaviour model unavailable "
                f"({self._india_load_error or 'disabled'}); falling back to IEEE-CIS "
                "canonical mapping with low feature coverage."
            )

        # --- Feature extraction ---
        xgb_features = canonical_to_xgb_features(transaction)
        if_features = canonical_to_if_features(transaction)
        mapping_desc = describe_mapping()

        n_mapped = len(xgb_features)
        total_features = mapping_desc["total_ieee_cis_features"]
        n_nan_imputed = total_features - n_mapped

        feature_mapping = FeatureMappingInfo(
            scoring_mode=ScoringMode.CANONICAL_MAPPED,
            n_features_mapped=n_mapped,
            total_model_features=total_features,
            n_nan_imputed=n_nan_imputed,
            mapped_fields=list(xgb_features.keys()),
            mapping_warning=(
                f"Only {n_mapped} of {total_features} IEEE-CIS features are available "
                f"from CanonicalTransaction. {n_nan_imputed} features are NaN-imputed. "
                "Model accuracy is reduced relative to full IEEE-CIS benchmarks. "
                "Results should be treated as indicative only."
            ),
        )
        warnings.append(
            f"Low feature coverage: {n_mapped}/{total_features} features mapped. "
            f"{n_nan_imputed} features NaN-imputed."
        )

        # --- XGBoost scoring ---
        xgb_result_dict = self._run_xgboost(xgb_features, errors)
        xgb_detail = self._build_xgb_detail(xgb_result_dict)

        # --- SHAP explanations ---
        shap_result = self._run_shap(xgb_features, warnings, errors)

        # --- Isolation Forest scoring ---
        if_result_dict = self._run_isolation_forest(if_features, errors)
        if_detail = self._build_if_detail(if_result_dict)

        # --- Build deviation features ---
        top_features = self._build_deviation_features(shap_result, xgb_features)

        # --- Score fields ---
        anomaly_score = (
            xgb_detail.fraud_probability if xgb_detail is not None else None
        )
        isolation_score = (
            if_detail.anomaly_score if if_detail is not None else None
        )

        # --- Combined confidence ---
        combined_confidence = None
        if anomaly_score is not None and isolation_score is not None:
            try:
                if_thr = (
                    self._if_threshold
                    if self._if_threshold is not None
                    else _DEFAULT_IF_CALIBRATED_THRESHOLD
                )
                combined_confidence = _compute_combined_confidence(
                    xgb_prob=anomaly_score,
                    if_anomaly_score=isolation_score,
                    xgb_weight=self._xgb_weight,
                    if_weight=self._if_weight,
                    if_threshold=if_thr,
                )
            except Exception as exc:
                errors.append(f"combined_confidence calculation error: {exc}")
                logger.error("combined_confidence failed: %s", exc)
        else:
            missing = []
            if anomaly_score is None:
                missing.append("XGBoost")
            if isolation_score is None:
                missing.append("Isolation Forest")
            warnings.append(
                f"combined_confidence is None because the following models are "
                f"unavailable: {', '.join(missing)}."
            )

        # --- Determine overall status ---
        status = self._determine_status(
            xgb_detail=xgb_detail,
            if_detail=if_detail,
            shap_available=shap_result is not None,
            errors=errors,
        )

        return Agent1Output(
            transaction_id=tx_id,
            source_dataset=source_ds,
            scored_at_utc=scored_at,
            status=status,
            warnings=warnings,
            errors=errors,
            anomaly_score=anomaly_score,
            isolation_score=isolation_score,
            combined_confidence=combined_confidence,
            top_deviation_features=top_features,
            xgboost_detail=xgb_detail,
            isolation_forest_detail=if_detail,
            shap_available=shap_result is not None,
            shap_base_value=shap_result.get("base_value") if shap_result else None,
            shap_sum=shap_result.get("shap_sum") if shap_result else None,
            feature_mapping=feature_mapping,
            combined_confidence_note=COMBINED_CONFIDENCE_NOTE,
        )

    def score_raw(
        self,
        features: dict[str, Any],
        transaction_id: Optional[str] = None,
    ) -> Agent1Output:
        """Score a raw IEEE-CIS feature dict (bypasses CanonicalTransaction mapping).

        Use this when the caller has already prepared the full or partial
        feature dict, e.g. when scoring directly from the IEEE-CIS dataset
        during evaluation.

        Parameters
        ----------
        features       : dict with IEEE-CIS feature keys.
        transaction_id : optional identifier for provenance.

        Returns
        -------
        Agent1Output
        """
        scored_at = datetime.now(timezone.utc)
        warnings: list[str] = []
        errors: list[str] = []

        n_mapped = len(features)
        total_features = 432  # IEEE-CIS feature count
        n_nan_imputed = max(0, total_features - n_mapped)

        feature_mapping = FeatureMappingInfo(
            scoring_mode=ScoringMode.RAW_FEATURES,
            n_features_mapped=n_mapped,
            total_model_features=total_features,
            n_nan_imputed=n_nan_imputed,
            mapped_fields=list(features.keys())[:50],  # cap list length for output
            mapping_warning=(
                None if n_nan_imputed == 0
                else f"{n_nan_imputed} features absent from raw dict; will be NaN-imputed."
            ),
        )
        if n_nan_imputed > 0:
            warnings.append(f"{n_nan_imputed} features NaN-imputed from raw dict.")

        # --- XGBoost ---
        xgb_result_dict = self._run_xgboost(features, errors)
        xgb_detail = self._build_xgb_detail(xgb_result_dict)

        # --- SHAP ---
        shap_result = self._run_shap(features, warnings, errors)

        # --- IF ---
        if_result_dict = self._run_isolation_forest(features, errors)
        if_detail = self._build_if_detail(if_result_dict)

        top_features = self._build_deviation_features(shap_result, features)

        anomaly_score = xgb_detail.fraud_probability if xgb_detail is not None else None
        isolation_score = if_detail.anomaly_score if if_detail is not None else None

        combined_confidence = None
        if anomaly_score is not None and isolation_score is not None:
            try:
                if_thr = (
                    self._if_threshold
                    if self._if_threshold is not None
                    else _DEFAULT_IF_CALIBRATED_THRESHOLD
                )
                combined_confidence = _compute_combined_confidence(
                    xgb_prob=anomaly_score,
                    if_anomaly_score=isolation_score,
                    xgb_weight=self._xgb_weight,
                    if_weight=self._if_weight,
                    if_threshold=if_thr,
                )
            except Exception as exc:
                errors.append(f"combined_confidence calculation error: {exc}")

        status = self._determine_status(
            xgb_detail=xgb_detail,
            if_detail=if_detail,
            shap_available=shap_result is not None,
            errors=errors,
        )

        return Agent1Output(
            transaction_id=transaction_id,
            source_dataset=None,
            scored_at_utc=scored_at,
            status=status,
            warnings=warnings,
            errors=errors,
            anomaly_score=anomaly_score,
            isolation_score=isolation_score,
            combined_confidence=combined_confidence,
            top_deviation_features=top_features,
            xgboost_detail=xgb_detail,
            isolation_forest_detail=if_detail,
            shap_available=shap_result is not None,
            shap_base_value=shap_result.get("base_value") if shap_result else None,
            shap_sum=shap_result.get("shap_sum") if shap_result else None,
            feature_mapping=feature_mapping,
            combined_confidence_note=COMBINED_CONFIDENCE_NOTE,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _score_india(self, transaction, tx_id, source_ds, scored_at) -> Agent1Output:
        """Score with the India behavioural model (ScoringMode.INDIA_NATIVE)."""
        from ...ml.india_behaviour_model import FEATURES, feature_coverage

        warnings: list[str] = []
        errors: list[str] = []
        try:
            r = self._india_scorer.score(transaction, top_n=self._top_n_shap)
        except Exception as exc:  # noqa: BLE001
            logger.error("India model scoring failed: %s", exc)
            return Agent1Output(
                transaction_id=tx_id, source_dataset=source_ds, scored_at_utc=scored_at,
                status=AgentStatus.FAILED, errors=[f"India model inference error: {type(exc).__name__}"],
            )
        feats = r["features"]
        n_mapped = feature_coverage(feats)
        mapping = FeatureMappingInfo(
            scoring_mode=ScoringMode.INDIA_NATIVE,
            n_features_mapped=n_mapped,
            total_model_features=len(FEATURES),
            n_nan_imputed=len(FEATURES) - n_mapped,
            mapped_fields=[k for k, v in feats.items() if v == v],
            mapping_warning=None if n_mapped == len(FEATURES) else
            f"{len(FEATURES) - n_mapped} of {len(FEATURES)} India behavioural features unavailable.",
        )
        prob = r["fraud_probability"]
        xgb_detail = XGBoostDetail(
            fraud_probability=prob,
            is_fraud_predicted=prob >= r["xgb_threshold"],
            threshold_used=r["xgb_threshold"],
            model_version=r["model_version"],
            note=("India behavioural XGBoost trained on SYNTHETIC labels. Statistical "
                  "signal only, not proof of fraud."),
        )
        if_detail = IsolationForestDetail(
            anomaly_score=r["if_anomaly_score"],
            is_anomaly=r["if_anomaly_score"] >= r["if_threshold"],
            threshold_used=r["if_threshold"],
            model_version=r["model_version"],
            score_note="Isolation Forest anomaly score (higher = more unusual). Not a probability.",
        )
        combined = _compute_combined_confidence(
            xgb_prob=prob, if_anomaly_score=r["if_anomaly_score"],
            xgb_weight=self._xgb_weight, if_weight=self._if_weight, if_threshold=r["if_threshold"],
        )
        shap = r["shap"]
        if shap is None:
            warnings.append("SHAP explanation unavailable for India model.")
        if mapping.mapping_warning:
            warnings.append(mapping.mapping_warning)
        status = AgentStatus.COMPLETE if (shap is not None and n_mapped == len(FEATURES)) else AgentStatus.PARTIAL
        return Agent1Output(
            transaction_id=tx_id,
            source_dataset=source_ds,
            scored_at_utc=scored_at,
            status=status,
            warnings=warnings,
            errors=errors,
            anomaly_score=prob,
            isolation_score=r["if_anomaly_score"],
            combined_confidence=combined,
            top_deviation_features=self._build_deviation_features(shap, feats),
            xgboost_detail=xgb_detail,
            isolation_forest_detail=if_detail,
            shap_available=shap is not None,
            shap_base_value=shap.get("base_value") if shap else None,
            shap_sum=shap.get("shap_sum") if shap else None,
            feature_mapping=mapping,
            combined_confidence_note=COMBINED_CONFIDENCE_NOTE + (
                " For INDIA_NATIVE scoring the IF sigmoid is centred on the India "
                "model's calibrated IF threshold."
            ),
        )

    def _run_xgboost(
        self,
        features: dict[str, Any],
        errors: list[str],
    ) -> Optional[dict[str, Any]]:
        """Run XGBoost prediction. Returns result dict or None on inference failure."""
        # _xgb_predictor is always set after successful __init__.
        # None here means it was replaced by a test mock that set it to None.
        if self._xgb_predictor is None:
            errors.append("XGBoost model unavailable.")
            return None
        try:
            return self._xgb_predictor.predict_transaction(
                features, threshold=self._xgb_threshold
            )
        except Exception as exc:
            errors.append(f"XGBoost inference error: {exc}")
            logger.error("XGBoost inference failed: %s", exc)
            return None

    def _run_isolation_forest(
        self,
        features: dict[str, Any],
        errors: list[str],
    ) -> Optional[dict[str, Any]]:
        """Run IF scoring. Returns result dict or None on inference failure."""
        # _if_predictor is always set after successful __init__.
        if self._if_predictor is None:
            errors.append("Isolation Forest model unavailable.")
            return None
        try:
            return self._if_predictor.score_transaction(
                features, threshold=self._if_threshold
            )
        except Exception as exc:
            errors.append(f"Isolation Forest inference error: {exc}")
            logger.error("IF inference failed: %s", exc)
            return None

    def _run_shap(
        self,
        features: dict[str, Any],
        warnings: list[str],
        errors: list[str],
    ) -> Optional[dict[str, Any]]:
        """Run SHAP explanation for XGBoost. Returns explanation dict or None."""
        if self._xgb_predictor is None:
            warnings.append("SHAP unavailable: XGBoost model not set.")
            return None
        try:
            import pandas as pd
            df = pd.DataFrame([features])
            for col in ("TransactionID", "isFraud"):
                if col in df.columns:
                    df = df.drop(columns=[col])
            df = df.reindex(columns=self._xgb_predictor.feature_names)
            X_t = self._xgb_predictor._pipeline.transform(df)
            x_row = X_t[0]

            shap_result = explain_prediction(
                self._xgb_predictor._model,
                x_row,
                self._xgb_predictor.feature_names,
                top_n=self._top_n_shap,
            )
            return shap_result
        except Exception as exc:
            warnings.append(f"SHAP explanation unavailable: {exc}")
            logger.warning("SHAP computation failed: %s", exc)
            return None

    def _build_xgb_detail(
        self, result: Optional[dict[str, Any]]
    ) -> Optional[XGBoostDetail]:
        """Convert raw XGBoost dict to typed XGBoostDetail. Returns None on failure."""
        if result is None:
            return None
        try:
            return XGBoostDetail(
                fraud_probability=result["fraud_probability"],
                is_fraud_predicted=result["is_fraud_predicted"],
                threshold_used=result["threshold_used"],
                model_version=result.get("model_version"),
                note=result.get("note", ""),
            )
        except (KeyError, ValidationError) as exc:
            logger.error("Failed to build XGBoostDetail: %s", exc)
            return None

    def _build_if_detail(
        self, result: Optional[dict[str, Any]]
    ) -> Optional[IsolationForestDetail]:
        """Convert raw IF dict to typed IsolationForestDetail. Returns None on failure."""
        if result is None:
            return None
        try:
            return IsolationForestDetail(
                anomaly_score=result["anomaly_score"],
                is_anomaly=result["is_anomaly"],
                threshold_used=result["threshold_used"],
                model_version=result.get("model_version"),
                score_note=result.get("score_note", ""),
            )
        except (KeyError, ValidationError) as exc:
            logger.error("Failed to build IsolationForestDetail: %s", exc)
            return None

    def _build_deviation_features(
        self,
        shap_result: Optional[dict[str, Any]],
        features: dict[str, Any],
    ) -> list[DeviationFeature]:
        """Build DeviationFeature list from SHAP output.

        Features are ranked by absolute SHAP value (rank 1 = most influential).
        Feature values are included when the preprocessed value is safely available.
        NaN-imputed features (not in the original feature dict) have feature_value=None.
        """
        if shap_result is None:
            return []

        contributors = shap_result.get("top_contributors", [])
        deviation_features = []
        for rank_idx, contributor in enumerate(contributors, start=1):
            feat_name = contributor["feature"]
            shap_val = contributor["shap_value"]
            direction = contributor["direction"]

            # Include the raw (pre-preprocessing) feature value when available.
            # We do NOT attempt to reverse the preprocessing to recover the value.
            raw_val = features.get(feat_name)
            if raw_val is not None:
                try:
                    feat_value = float(raw_val)
                except (TypeError, ValueError):
                    feat_value = None
            else:
                feat_value = None  # NaN-imputed — report as None, not as 0.0

            deviation_features.append(
                DeviationFeature(
                    feature=feat_name,
                    shap_value=shap_val,
                    direction=direction,
                    feature_value=feat_value,
                    rank=rank_idx,
                )
            )
        return deviation_features

    def _determine_status(
        self,
        xgb_detail: Optional[XGBoostDetail],
        if_detail: Optional[IsolationForestDetail],
        shap_available: bool,
        errors: list[str],
    ) -> AgentStatus:
        """Determine the AgentStatus from the available outputs."""
        if xgb_detail is None and if_detail is None:
            return AgentStatus.FAILED

        if xgb_detail is not None and if_detail is not None and shap_available:
            # Both models and SHAP available → COMPLETE (with canonical-mapping warning)
            return AgentStatus.COMPATIBILITY_WARNING

        # At least one model available
        return AgentStatus.PARTIAL

    @property
    def xgb_available(self) -> bool:
        return self._xgb_predictor is not None

    @property
    def if_available(self) -> bool:
        return self._if_predictor is not None

    @property
    def both_models_available(self) -> bool:
        return self.xgb_available and self.if_available

    @property
    def xgb_metadata(self) -> Optional[dict[str, Any]]:
        if self._xgb_predictor is not None:
            return dict(self._xgb_predictor.metadata)
        return None

    @property
    def if_metadata(self) -> Optional[dict[str, Any]]:
        if self._if_predictor is not None:
            return dict(self._if_predictor.metadata)
        return None
