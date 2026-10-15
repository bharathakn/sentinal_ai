# FILE: docs/plans/CURRENT.md

# Current Project State

## Project

Sentinel AI

## Current Phase

Phase 2 — Data and ML (COMPLETE).
Phase 3 — Model Evaluation + Explainability (COMPLETE).

## Current Objective

Agent 1 LangGraph integration — blocked pending `feature/canonical-schema` merge.

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
  - Metrics evaluator: accuracy, precision, recall, F1, ROC-AUC, PR-AUC, FPR, FNR, confusion matrix (`src/ml/evaluator.py`)
  - SHAP explainability: global importance + per-prediction attribution (`src/ml/explainer.py`)
  - Actual evaluation (15% IEEE-CIS sample): PR-AUC=0.662, ROC-AUC=0.934
- **Isolation Forest anomaly detection — IMPLEMENTED AND VERIFIED (Phase 2)**
  - Unsupervised trainer reusing shared preprocessing (`src/ml/if_trainer.py`)
  - Inference predictor with score convention documented (`src/ml/if_predictor.py`)
  - IF evaluator with FPR, FNR, caveat text (`src/ml/if_evaluator.py`)
  - Training script: `scripts/train_isolation_forest.py`
  - Actual evaluation (15% IEEE-CIS sample): ROC-AUC=0.804, PR-AUC=0.178 (~5× random)
  - Artifact reload verified: max_diff=0.00e+00
- **Phase 3 — Model Evaluation + Explainability — IMPLEMENTED AND VERIFIED**
  - Threshold calibration module with test-set isolation (`src/ml/threshold_calibration.py`)
  - XGBoost calibrated threshold=0.80: F1=0.615, Precision=0.714, Recall=0.540, FPR=0.008
  - IF calibrated threshold=0.468: F1=0.293, FPR=0.035, FNR=0.667 (unsupervised — annotated)
  - Threshold calibration script: `scripts/run_threshold_calibration.py`
  - CanonicalTransaction → IEEE-CIS feature mapper (`src/ml/feature_mapper.py`)
  - Agent 1 ML scoring integration (`src/ml/agent1_scorer.py`) — LangGraph wiring pending
  - 170 total tests — all passing
  - Documentation: `THRESHOLD_CALIBRATION.md` (new), `ML_OVERVIEW.md` (updated)

## In Progress

Nothing.

## Next Major Milestones

1. Agent 1 LangGraph node wiring (blocked: `feature/canonical-schema` branch not merged)
2. Full-dataset XGBoost + IF training (remove SENTINEL_SAMPLE_FRAC)
3. Neo4j graph database setup & bulk ingestion (Agent 3)
4. FastAPI ingestion
5. Agent 2
6. Agent 3
7. Agent 4
8. Agent 5
9. Output Validator
10. LangGraph integration
11. MongoDB persistence
12. Dashboard
13. Evaluation
14. End-to-end testing

## Current Blockers

**Agent 1 LangGraph wiring** — `src/ml/agent1_scorer.py` (ML inference layer) is ready.
Blocked pending merge of `feature/canonical-schema` branch which contains the
CanonicalTransaction Pydantic model. The graph node itself has not yet been written.

## Important Rule

Update this document whenever the active development phase changes.