# FILE: docs/plans/CURRENT.md

# Current Project State

## Project

Sentinel AI

## Current Phase

Phase 2 — Data and ML (XGBoost + Isolation Forest complete).

## Current Objective

IF threshold calibration and Agent 1 integration (XGBoost + IF → LangGraph Agent 1).

## Completed

- Project concept defined
- Five-agent architecture defined
- Investigation flow defined
- Technology stack selected (Groq API, MongoDB Atlas, Neo4j, FastAPI, React, Mock Banking APIs)
- Prototype datasets identified & raw dataset directories organized (`dataset/raw/ieee_cis`, `dataset/raw/paysim`, `dataset/raw/regulatory/`, `dataset/raw/sanctions/`)
- Repository structure and documentation audit initialized
- Evidence sources identified
- Dashboard requirements identified
- Validation architecture defined
- Custom Synthetic India Dataset generated and validated (STATUS: COMPLETED & VERIFIED — SYNTHETIC DATA)
- **XGBoost fraud detection pipeline — IMPLEMENTED AND VERIFIED (Phase 2)**
  - IEEE-CIS dataset loading and merging (`src/ml/ieee_cis_loader.py`)
  - Reusable sklearn preprocessing pipeline (`src/ml/preprocessor.py`)
  - XGBoost trainer with stratified splits, class-imbalance weighting, early stopping (`src/ml/trainer.py`)
  - Inference predictor loading saved artifacts (`src/ml/predictor.py`)
  - Metrics evaluator: precision, recall, F1, ROC-AUC, PR-AUC, confusion matrix (`src/ml/evaluator.py`)
  - SHAP explainability: global importance + per-prediction attribution (`src/ml/explainer.py`)
  - Actual evaluation (15% IEEE-CIS sample): PR-AUC=0.662, ROC-AUC=0.934
- **Isolation Forest anomaly detection — IMPLEMENTED AND VERIFIED (Phase 2)**
  - Unsupervised trainer reusing shared preprocessing (`src/ml/if_trainer.py`)
  - Inference predictor with score convention documented (`src/ml/if_predictor.py`)
  - IF evaluator with caveat text (`src/ml/if_evaluator.py`)
  - Training script: `scripts/train_isolation_forest.py`
  - 109 total tests — all passing
  - Actual evaluation (15% IEEE-CIS sample): ROC-AUC=0.804, PR-AUC=0.178 (~5× random)
  - Threshold calibration needed before deployment
  - Artifact reload verified: max_diff=0.00e+00

## In Progress

Nothing.

## Next Major Milestones

1. IF threshold calibration on validation data
2. Full-dataset XGBoost + IF training (remove SENTINEL_SAMPLE_FRAC)
3. Agent 1 (Anomaly Detector — wire XGBoost + IF into LangGraph)
4. Neo4j graph database setup & bulk ingestion (Agent 3)
5. FastAPI ingestion
6. Agent 2
7. Agent 3
8. Agent 4
9. Agent 5
10. Output Validator
11. LangGraph integration
12. MongoDB persistence
13. Dashboard
14. Evaluation
15. End-to-end testing

## Current Blockers

None documented.

## Important Rule

Update this document whenever the active development phase changes.