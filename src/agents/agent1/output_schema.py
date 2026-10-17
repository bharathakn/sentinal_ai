"""
Sentinel AI — Agent 1 structured output schema.

This module defines the validated Pydantic output contract for Agent 1
(Anomaly Detector). All downstream agents and the orchestration layer
consume this schema.

Design rules
------------
* None is the sentinel for "score not available". A score of 0.0 is a
  genuine score value, never a stand-in for unavailability.
* combined_confidence is NOT a calibrated fraud probability. It is an
  heuristic signal. Its definition is documented in CombinedConfidenceNote.
* All score fields carry their valid range in field metadata.
* The schema is frozen (immutable after construction) to prevent
  accidental mutation in a multi-agent pipeline.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class AgentStatus(str, Enum):
    """Overall result status of the Agent 1 run."""

    COMPLETE = "COMPLETE"
    """Both models scored successfully and SHAP explanations are available."""

    PARTIAL = "PARTIAL"
    """At least one model scored, but some components failed (e.g. SHAP unavailable)."""

    FAILED = "FAILED"
    """Critical failure: no model could score the transaction."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    """Transaction failed input validation before reaching scoring."""

    COMPATIBILITY_WARNING = "COMPATIBILITY_WARNING"
    """Transaction was scored, but with a documented low-coverage feature mapping."""


class ScoringMode(str, Enum):
    """Describes how the transaction was scored."""

    CANONICAL_MAPPED = "CANONICAL_MAPPED"
    """Scored via CanonicalTransaction → feature mapper. Most features NaN-imputed."""

    RAW_FEATURES = "RAW_FEATURES"
    """Scored with a full or partial IEEE-CIS feature dict (bypasses mapper)."""


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class DeviationFeature(BaseModel):
    """A single feature attribution entry in the top-deviation list.

    Populated from SHAP explanations. SHAP values describe the model's
    feature attribution for this specific prediction. They do NOT prove
    fraudulent intent.
    """

    model_config = ConfigDict(frozen=True)

    feature: str = Field(description="IEEE-CIS feature name.")
    shap_value: float = Field(
        description=(
            "SHAP attribution value. Positive values push the prediction "
            "toward fraud; negative values push away from fraud. "
            "Magnitude indicates relative importance for this prediction."
        )
    )
    direction: str = Field(
        description=(
            "'increases_fraud_score' or 'decreases_fraud_score'. "
            "Based on the sign of shap_value."
        )
    )
    feature_value: Optional[float] = Field(
        default=None,
        description=(
            "Preprocessed numeric value of the feature for this transaction. "
            "None when the feature was NaN-imputed or not safely available."
        ),
    )
    rank: int = Field(
        description="Rank by absolute SHAP value magnitude (1 = most influential)."
    )


class XGBoostDetail(BaseModel):
    """XGBoost model output for one transaction."""

    model_config = ConfigDict(frozen=True)

    fraud_probability: float = Field(
        ge=0.0, le=1.0,
        description=(
            "Supervised fraud probability from XGBoost binary:logistic objective. "
            "Range [0, 1]. This is a statistical signal, NOT proof of fraud."
        ),
    )
    is_fraud_predicted: bool = Field(
        description="True when fraud_probability >= threshold_used."
    )
    threshold_used: float = Field(
        description="Classification threshold applied to fraud_probability."
    )
    model_version: Optional[str] = Field(
        default=None, description="Version string from model metadata."
    )
    note: str = Field(
        description="Interpretation disclaimer."
    )


class IsolationForestDetail(BaseModel):
    """Isolation Forest model output for one transaction."""

    model_config = ConfigDict(frozen=True)

    anomaly_score: float = Field(
        description=(
            "Isolation Forest anomaly score = -score_samples(). "
            "Higher values indicate greater statistical unusualness. "
            "This is NOT a probability. Scale differs from XGBoost fraud_probability."
        )
    )
    is_anomaly: bool = Field(
        description="True when anomaly_score >= threshold_used."
    )
    threshold_used: float = Field(
        description="Decision threshold applied to anomaly_score."
    )
    model_version: Optional[str] = Field(
        default=None, description="Version string from model metadata."
    )
    score_note: str = Field(
        description="Interpretation disclaimer."
    )


class FeatureMappingInfo(BaseModel):
    """Summary of the canonical-to-model feature mapping applied."""

    model_config = ConfigDict(frozen=True)

    scoring_mode: ScoringMode
    n_features_mapped: int = Field(
        description="Number of features populated from the canonical transaction."
    )
    total_model_features: int = Field(
        description="Total number of features the model expects."
    )
    n_nan_imputed: int = Field(
        description="Number of features that will be NaN-imputed by the preprocessor."
    )
    mapped_fields: list[str] = Field(
        description="IEEE-CIS column names that were populated."
    )
    mapping_warning: Optional[str] = Field(
        default=None,
        description=(
            "Warning message when the mapping coverage is low. "
            "Low coverage means the model is operating mostly on imputed values, "
            "which degrades accuracy relative to IEEE-CIS benchmarks."
        ),
    )


# ---------------------------------------------------------------------------
# Combined confidence documentation
# ---------------------------------------------------------------------------

COMBINED_CONFIDENCE_NOTE = (
    "combined_confidence is a heuristic signal, NOT a calibrated fraud probability. "
    "Strategy: XGBoost fraud_probability (range [0,1]) is directly usable as a "
    "probability-like score. The Isolation Forest anomaly_score has a different scale "
    "and cannot be directly compared. "
    "combined_confidence = weighted average of:"
    " (a) xgb_fraud_probability (weight=0.70) and"
    " (b) IF signal clipped to [0,1] via sigmoid normalisation of anomaly_score"
    "     relative to the calibrated IF threshold (weight=0.30). "
    "Weights reflect the relative reliability of each model: XGBoost is calibrated "
    "and supervised; IF is unsupervised and has lower precision (PR-AUC=0.178 vs "
    "XGBoost PR-AUC=0.662). "
    "combined_confidence is NOT fit on the test set. "
    "It is a convenience composite for ranking. "
    "Do not interpret it as P(fraud). "
    "When either model score is unavailable, combined_confidence is None."
)


# ---------------------------------------------------------------------------
# Main output model
# ---------------------------------------------------------------------------


class Agent1Output(BaseModel):
    """Structured output for Agent 1 (Anomaly Detector).

    This is the canonical output contract for Agent 1. All fields are
    explicitly typed and documented. None is used for genuinely unavailable
    values; 0.0 is never substituted as a missing-score sentinel.

    Downstream agents must check status and warnings before consuming scores.
    """

    model_config = ConfigDict(frozen=True)

    # ------------------------------------------------------------------
    # Identity and provenance
    # ------------------------------------------------------------------
    transaction_id: Optional[str] = Field(
        default=None,
        description="raw_record_id from the CanonicalTransaction, if available.",
    )
    source_dataset: Optional[str] = Field(
        default=None,
        description="source_dataset from the CanonicalTransaction, if available.",
    )
    scored_at_utc: datetime = Field(
        description="UTC timestamp when Agent 1 produced this result."
    )

    # ------------------------------------------------------------------
    # Agent status
    # ------------------------------------------------------------------
    status: AgentStatus = Field(
        description="Overall result status. Check before consuming scores."
    )
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Non-fatal warnings, e.g. low feature coverage or SHAP unavailable. "
            "An empty list means no warnings."
        ),
    )
    errors: list[str] = Field(
        default_factory=list,
        description=(
            "Error messages for failed components. "
            "If status == FAILED, at least one error is present."
        ),
    )

    # ------------------------------------------------------------------
    # Core score fields (required by specification)
    # ------------------------------------------------------------------
    anomaly_score: Optional[float] = Field(
        default=None,
        description=(
            "XGBoost fraud_probability ∈ [0, 1]. Named anomaly_score for "
            "compatibility with the Phase 4 output contract. "
            "Represents the supervised model's estimate of fraud likelihood. "
            "None when the XGBoost model is unavailable."
        ),
    )
    isolation_score: Optional[float] = Field(
        default=None,
        description=(
            "Isolation Forest anomaly_score = -score_samples(). "
            "Higher = more statistically unusual. NOT a probability. "
            "Scale differs from anomaly_score. "
            "None when the Isolation Forest model is unavailable."
        ),
    )
    combined_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Heuristic composite of XGBoost and IF signals. "
            "See combined_confidence_note for the full definition. "
            "None when either model is unavailable. "
            "NOT a calibrated probability of fraud."
        ),
    )
    top_deviation_features: list[DeviationFeature] = Field(
        default_factory=list,
        description=(
            "Top features by absolute SHAP attribution, ranked descending. "
            "Empty when SHAP is unavailable. "
            "These are model attribution features, not statistically anomalous "
            "population deviations."
        ),
    )

    # ------------------------------------------------------------------
    # Extended model detail
    # ------------------------------------------------------------------
    xgboost_detail: Optional[XGBoostDetail] = Field(
        default=None,
        description=(
            "Full XGBoost result including classification, threshold, and model version. "
            "None when the XGBoost model is unavailable."
        ),
    )
    isolation_forest_detail: Optional[IsolationForestDetail] = Field(
        default=None,
        description=(
            "Full Isolation Forest result including classification and model version. "
            "None when the IF model is unavailable."
        ),
    )

    # ------------------------------------------------------------------
    # Explainability metadata
    # ------------------------------------------------------------------
    shap_available: bool = Field(
        default=False,
        description="True when SHAP explanations were successfully computed.",
    )
    shap_base_value: Optional[float] = Field(
        default=None,
        description=(
            "SHAP TreeExplainer expected_value (base rate in log-odds). "
            "None when SHAP is unavailable."
        ),
    )
    shap_sum: Optional[float] = Field(
        default=None,
        description=(
            "Sum of all SHAP values for this prediction (= log-odds shift from base). "
            "None when SHAP is unavailable."
        ),
    )

    # ------------------------------------------------------------------
    # Feature mapping
    # ------------------------------------------------------------------
    feature_mapping: Optional[FeatureMappingInfo] = Field(
        default=None,
        description="Summary of how transaction fields were mapped to model features.",
    )

    # ------------------------------------------------------------------
    # Combination strategy documentation
    # ------------------------------------------------------------------
    combined_confidence_note: str = Field(
        default=COMBINED_CONFIDENCE_NOTE,
        description="Documents the combined_confidence calculation strategy and limitations.",
    )
