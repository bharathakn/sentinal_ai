# FILE: docs/04_MACHINE_LEARNING/ML_OVERVIEW.md

# Machine Learning Overview

## Purpose

Machine learning is primarily used by the Anomaly Detector (Agent 1).

## Models

### XGBoost

Primary supervised fraud detection model.

Status: **IMPLEMENTED AND VERIFIED** — see `XGBOOST_PIPELINE.md`.

Output key: `fraud_probability` ∈ [0, 1] — supervised probability estimate.

### Isolation Forest

Secondary unsupervised anomaly detection model.

Status: **IMPLEMENTED AND VERIFIED** — see `ISOLATION_FOREST_PIPELINE.md`.

Output key: `anomaly_score` ∈ ℝ (higher = more anomalous). **Not a fraud probability.**

Must NOT be combined with XGBoost `fraud_probability` without a tested fusion strategy.

### SHAP

Explainability layer for XGBoost feature contribution. Implemented in `src/ml/explainer.py`.

SHAP values describe model behavior, not proof of fraud.

## Threshold Calibration

Status: **IMPLEMENTED** — see `THRESHOLD_CALIBRATION.md`.

Threshold calibration uses the VALIDATION split only. The test set is evaluated once after selection.

## Agent 1 Integration

Status: **ML LAYER COMPLETE — GRAPH WIRING PENDING**

`src/ml/agent1_scorer.py` provides the ML inference entry point for Agent 1.
`src/ml/feature_mapper.py` provides CanonicalTransaction → IEEE-CIS feature mapping.

LangGraph node wiring is blocked pending merge of the `feature/canonical-schema` branch.

## Dataset

Primary dataset for training and evaluation:

**IEEE-CIS Fraud Detection Dataset** — `dataset/raw/ieee_cis/`

Supplementary dataset:

PaySim.

Additional dataset:

Custom Synthetic India Dataset — for Indian scenario testing only.

Do NOT combine IEEE-CIS and India Synthetic results or present one as the other.

## Evaluated Metrics (Phase 3)

All metrics below are from ACTUAL evaluation runs. They are NOT targets.

Full definitions: see `EVALUATION_RESULTS.md`.

| Metric | Description |
|---|---|
| Accuracy | Overall correct predictions / total |
| Precision | TP / (TP + FP) |
| Recall | TP / (TP + FN) |
| F1-score | Harmonic mean of precision and recall |
| ROC-AUC | Area under ROC curve (threshold-independent) |
| PR-AUC | Area under Precision-Recall curve (primary for imbalance) |
| False Positive Rate | FP / (FP + TN) |
| False Negative Rate | FN / (FN + TP) |

## Important Principles

* Reported performance metrics must be from actual evaluation runs.
* The project documentation must distinguish planned target values from measured results.
* Threshold selection uses the validation split only. Test set is evaluated once.
* XGBoost and IF outputs are kept separate. Neither is proof of fraud.
* SHAP values are explanations of model behavior, not causal fraud evidence.