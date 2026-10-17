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

Status: **PHASE 4 COMPLETE — AGENT 1 ANOMALY DETECTOR IMPLEMENTED AND TESTED**

### Phase 4 implementation

- `src/agents/agent1/anomaly_detector.py` — `AnomalyDetectorAgent` (full processing flow)
- `src/agents/agent1/output_schema.py` — `Agent1Output` Pydantic schema with validated fields
- `src/ml/agent1_scorer.py` — lower-level ML scoring integration (preserved)
- `src/ml/feature_mapper.py` — CanonicalTransaction → IEEE-CIS feature mapping (preserved)

### Agent 1 data flow

```
CanonicalTransaction
  → canonical_to_xgb_features()       # feature_mapper.py
  → FraudPredictor.predict_transaction()  # XGBoost scoring
  → explain_prediction()               # SHAP per-prediction attributions
  → AnomalyPredictor.score_transaction()  # Isolation Forest scoring
  → _compute_combined_confidence()    # documented heuristic fusion
  → Agent1Output                       # validated Pydantic model
```

### Score semantics

- `anomaly_score` = XGBoost `fraud_probability` ∈ [0, 1] (supervised probability-like score)
- `isolation_score` = IF `-score_samples()` ∈ ℝ (higher = more anomalous; NOT a probability)
- `combined_confidence` = `0.70 × xgb_prob + 0.30 × sigmoid_if` ∈ [0, 1] (heuristic; NOT calibrated probability)
- `top_deviation_features` = top-N SHAP attributions ranked by absolute value

### LangGraph integration

LangGraph is not yet installed. `AnomalyDetectorAgent` is implemented as a standalone Python callable with explicit input/output contracts, ready for LangGraph node wiring once LangGraph is added to the stack.

## Datasets and Full-Data Capability

Primary dataset for training and evaluation:
- **IEEE-CIS Fraud Detection Dataset** — `dataset/raw/ieee_cis/` (590,540 raw transactions, 144,233 identity rows).
  - Software supports full-dataset training via `SENTINEL_SAMPLE_FRAC=full` or omitting the environment variable.
  - Baseline reported metrics below were evaluated on a **15% stratified sample** (88,581 transactions) for rapid development.
  - Full-dataset training requires $\ge 16\text{GB}$ available host RAM to avoid OOM conditions during pandas merge and preprocessing.

Supplementary dataset:
- **PaySim** — `dataset/raw/paysim/` (Synthetic mobile-money transactions for graph and network testing).

Additional dataset:
- **Custom Synthetic India Dataset** — `dataset/processed/custom_india/` (for Indian scenario testing only).

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