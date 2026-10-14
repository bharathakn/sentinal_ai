# FILE: docs/plans/CURRENT.md

# Current Project State

## Project

Sentinel AI

## Current Phase

Phase 2 — Data and ML (XGBoost pipeline complete).

## Current Objective

Isolation Forest implementation (Phase 2 secondary model).

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
  - Training script: `scripts/train_pipeline.py`
  - 61 unit tests — all passing (`tests/`)
  - Actual evaluation run on 15% IEEE-CIS sample: PR-AUC=0.662, ROC-AUC=0.934
  - Artifact reload consistency verified (max_diff=0.00e+00)

## In Progress

Nothing.

## Next Major Milestones

1. Isolation Forest (Phase 2 secondary model — unsupervised cross-check)
2. Full-dataset XGBoost training (remove SENTINEL_SAMPLE_FRAC)
3. Classification threshold tuning on validation set
4. Neo4j graph database setup & bulk ingestion (Agent 3)
5. FastAPI ingestion
6. Agent 1 (Anomaly Detector — wire XGBoost predictor)
7. Agent 2
8. Agent 3
9. Agent 4
10. Agent 5
11. Output Validator
12. LangGraph integration
13. MongoDB persistence
14. Dashboard
15. Evaluation
16. End-to-end testing

## Current Blockers

None documented.

## Important Rule

Update this document whenever the active development phase changes.