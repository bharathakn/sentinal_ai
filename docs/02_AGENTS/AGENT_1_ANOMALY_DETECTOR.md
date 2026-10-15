# FILE: docs/02_AGENTS/AGENT_1_ANOMALY_DETECTOR.md

# Agent 1 — Anomaly Detector

## Purpose

Determine how abnormal a financial transaction is relative to expected customer behavior using supervised and unsupervised machine learning models.

## Implementation Status

- **ML Inference Layer (Phases 2 & 3 — COMPLETE & VERIFIED)**:
  - Supervised fraud detection: XGBoost (`src/ml/trainer.py`, `src/ml/predictor.py`)
  - Unsupervised anomaly detection: Isolation Forest (`src/ml/if_trainer.py`, `src/ml/if_predictor.py`)
  - Feature mapping: `src/ml/feature_mapper.py` (CanonicalTransaction → model feature space)
  - Unified inference engine: `src/ml/agent1_scorer.py` (`Agent1Scorer`)
  - Explainability: SHAP (`src/ml/explainer.py`)
  - Threshold calibration: `src/ml/threshold_calibration.py` (XGBoost=0.80, IF=0.468)
- **LangGraph Agent Node (Phase 4 — PLANNED FOR NEXT WEEK)**:
  - Agent state node definition and graph compilation
  - Score fusion strategy (`combined_confidence`)
  - Agent output serialization
  - Normal, suspicious, malformed, and missing-feature scenario tests

## Models

### Primary Model: XGBoost (Supervised)
- Objective: `binary:logistic`
- Output: `fraud_probability` ∈ [0, 1]
- Calibrated threshold: `0.80` (Precision=0.714, Recall=0.540, F1=0.615)

### Secondary Model: Isolation Forest (Unsupervised)
- Detects statistical anomalies without using fraud labels during training.
- Output: `anomaly_score` ∈ ℝ (higher = more unusual; NOT a probability).
- Calibrated threshold: `0.468` (FPR=0.035, F1=0.293)
- Provides an independent cross-check on XGBoost.

## Behavioral Signals

The models evaluate transaction and identity signals:
- Transaction amount (`TransactionAmt`)
- Payment channel / Card network (`card1`–`card6`)
- Billing and shipping region codes (`addr1`, `addr2`)
- Purchaser and recipient email domains (`P_emaildomain`, `R_emaildomain`)
- Timedelta and count features (`D1`–`D15`, `C1`–`C14`)
- Vesta engineered fraud indicators (`V1`–`V339`)
- Device type, operating system, and browser strings (`DeviceInfo`, `DeviceType`, `id_01`–`id_38`)

## Agent Output Structure (Phase 4 Specification)

The final Agent 1 structured output produced for downstream agents will contain:
- `anomaly_score`: Supervised fraud probability from XGBoost
- `isolation_score`: Unsupervised anomaly score from Isolation Forest
- `combined_confidence`: Tested fusion score synthesizing both signals
- `top_deviation_features`: Top contributing features identified via SHAP
- `model_metadata`: Model version, thresholds used, evaluation dates

## Explainability (SHAP)

SHAP values are computed by `src/ml/explainer.py`. They indicate feature attribution for model reasoning, **not causal proof of fraud**.

## Handoff

The structured output is handed off to Agent 2 (Evidence Gatherer) and subsequently contributes to risk assessment in Agent 4.

## Core Rules

- Use structured output.
- Preserve model metadata and timestamps.
- Do not combine XGBoost probabilities and Isolation Forest scores without a validated fusion strategy.
- Treat generated AI output as untrusted until validated by the Output Validator.