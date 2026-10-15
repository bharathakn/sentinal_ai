# FILE: docs/plans/CURRENT.md

# Current Project State

## Project

Sentinel AI

## Current Phase

- Phase 1 — Canonical Transaction Schema & Data Adapters (INTEGRATED & VERIFIED).
- Phase 2 — ML Data Pipeline: XGBoost & Isolation Forest (COMPLETE & VERIFIED).
- Phase 3 — Model Evaluation + Explainability Foundation (COMPLETE & VERIFIED).

**Next Planned Phase**: Phase 4 — Agent 1 Anomaly Detector (LangGraph Node & State Integration) — explicitly scheduled for next week.

## Current Objective

Phase 3 final wrap-up and verification complete. Repository is fully verified, tested (264/264 tests passing), and ready for Phase 4.

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
- **Canonical Transaction Schema — INTEGRATED AND VERIFIED (Phase 1)**
  - Pydantic v2 `CanonicalTransaction` model with strict domain validators (`src/schemas/canonical_transaction.py`)
  - IEEE-CIS adapter (`src/schemas/adapters/ieee_cis_adapter.py`)
  - PaySim adapter (`src/schemas/adapters/paysim_adapter.py`)
  - India Synthetic adapter (`src/schemas/adapters/india_adapter.py`)
  - 82 canonical schema tests passing (`tests/test_canonical_schema.py`)
  - Schema documentation (`docs/16_DATA/CANONICAL_TRANSACTION_SCHEMA.md`)
- **XGBoost fraud detection pipeline — IMPLEMENTED AND VERIFIED (Phase 2)**
  - IEEE-CIS dataset loading and merging (`src/ml/ieee_cis_loader.py`)
  - Reusable sklearn preprocessing pipeline (`src/ml/preprocessor.py`)
  - XGBoost trainer with stratified splits, class-imbalance weighting, early stopping (`src/ml/trainer.py`)
  - Inference predictor loading saved artifacts (`src/ml/predictor.py`)
  - Metrics evaluator: accuracy, precision, recall, F1, ROC-AUC, PR-AUC, FPR, FNR, confusion matrix (`src/ml/evaluator.py`)
  - SHAP explainability: global importance + per-prediction attribution (`src/ml/explainer.py`)
  - Measured evaluation (15% IEEE-CIS sample, 8,859 test rows): PR-AUC=0.662, ROC-AUC=0.934
- **Isolation Forest anomaly detection — IMPLEMENTED AND VERIFIED (Phase 2)**
  - Unsupervised trainer reusing shared preprocessing (`src/ml/if_trainer.py`)
  - Inference predictor with score convention documented (`src/ml/if_predictor.py`)
  - IF evaluator with FPR, FNR, caveat text (`src/ml/if_evaluator.py`)
  - Training script: `scripts/train_isolation_forest.py`
  - Measured evaluation (15% IEEE-CIS sample, 8,859 test rows): ROC-AUC=0.804, PR-AUC=0.178 (~5× random)
  - Artifact reload verified: bitwise exact prediction match
- **Model Evaluation + Explainability Foundation — IMPLEMENTED AND VERIFIED (Phase 3)**
  - Threshold calibration module with strict test-set isolation (`src/ml/threshold_calibration.py`)
  - XGBoost calibrated threshold=0.80: Precision=0.714, Recall=0.540, F1=0.615, FPR=0.008, Accuracy=0.976
  - IF calibrated threshold=0.468: F1=0.293, FPR=0.035, FNR=0.667 (unsupervised anomaly caveat preserved)
  - Threshold calibration runner script: `scripts/run_threshold_calibration.py`
  - CanonicalTransaction → IEEE-CIS feature mapper (`src/ml/feature_mapper.py`) with support for real canonical schema adapters
  - Agent 1 ML scoring integration (`src/ml/agent1_scorer.py`) with full test coverage (`tests/test_agent1_scorer.py`)
  - 264 total automated tests across schemas and ML components — all passing
  - Documentation: `docs/04_MACHINE_LEARNING/THRESHOLD_CALIBRATION.md`, `docs/04_MACHINE_LEARNING/ML_OVERVIEW.md`

## Full-Dataset Evaluation Status and Hardware Limitations

- **Current Baseline**: 15% stratified IEEE-CIS sample (~88,581 transactions; 70,864 train, 8,858 validation, 8,859 test).
- **Full IEEE-CIS Dataset**: 590,540 raw transactions and 144,233 identity records (1.3GB raw CSV).
- **System Resource Audit**: 14GB total RAM, 5.2GB available RAM. Merging and preprocessing full 590k x 434 matrix in memory requires >=16GB available RAM. Attempting full training on this host triggers the Linux OOM-killer.
- **Reproducibility**: Training scripts (`src/ml/trainer.py` and `scripts/train_isolation_forest.py`) support full-dataset training by passing `sample_frac=None` (or omitting the flag) on a host with >=16GB RAM.

## Next Major Milestones (Phase 4 and Beyond)

1. **Phase 4: Agent 1 Anomaly Detector (LangGraph Node)**
   - Wire `Agent1Scorer` into LangGraph state node
   - Implement `combined_confidence` fusion strategy
   - Produce structured output: `anomaly_score`, `isolation_score`, `combined_confidence`, `top_deviation_features`
   - Normal, suspicious, malformed, missing-feature, and model-unavailable agent tests
2. Neo4j graph database setup & bulk ingestion (Agent 3)
3. FastAPI ingestion endpoint
4. Agent 2 (Evidence Gatherer)
5. Agent 3 (Network Analyser)
6. Agent 4 (Risk Assessor)
7. Agent 5 (Explanation Generator)
8. Output Validator (deterministic validation layer)
9. End-to-end multi-agent LangGraph integration
10. MongoDB persistence
11. Investigation Dashboard

## Current Blockers

None for Phase 2 or Phase 3. Phase 1 canonical schemas have been integrated into `feature/ml-evaluation`. All prerequisites for Phase 4 are satisfied.

## Important Rule

Update this document whenever the active development phase changes.