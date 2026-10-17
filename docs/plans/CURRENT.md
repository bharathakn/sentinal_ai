# FILE: docs/plans/CURRENT.md

# Current Project State

## Project

Sentinel AI

## Current Phase

- Phase 1 — Canonical Transaction Schema & Data Adapters (INTEGRATED & VERIFIED).
- Phase 2 — ML Data Pipeline: XGBoost & Isolation Forest (COMPLETE & VERIFIED).
- Phase 3 — Model Evaluation + Explainability Foundation (COMPLETE & VERIFIED).
- Phase 4 — Agent 1 Anomaly Detector (COMPLETE & VERIFIED).
- Phase 5 — Mock Evidence Infrastructure (COMPLETE & VERIFIED).

**Next Planned Phase**: Phase 6 — Agent 2 (Evidence Gatherer) + LangGraph orchestration.

## Current Objective

Phase 5 complete. 486/486 tests passing. Repository is verified and ready for Phase 6.

## Completed

- Project concept defined
- Five-agent architecture defined
- Investigation flow defined
- Technology stack selected (Groq API, MongoDB Atlas, Neo4j, FastAPI, React, Mock Banking APIs)
- Prototype datasets identified & raw dataset directories organized
- Repository structure and documentation audit initialized
- Evidence sources identified
- Dashboard requirements identified
- Validation architecture defined
- Custom Synthetic India Dataset generated and validated (STATUS: COMPLETED & VERIFIED — SYNTHETIC DATA)
- **Canonical Transaction Schema — INTEGRATED AND VERIFIED (Phase 1)**
  - Pydantic v2 `CanonicalTransaction` model (`src/schemas/canonical_transaction.py`)
  - IEEE-CIS, PaySim, India Synthetic adapters
  - 82 canonical schema tests passing
- **XGBoost fraud detection pipeline — IMPLEMENTED AND VERIFIED (Phase 2)**
  - Full IEEE-CIS pipeline, training, inference, evaluation
  - Measured: PR-AUC=0.662, ROC-AUC=0.934 (15% sample)
- **Isolation Forest anomaly detection — IMPLEMENTED AND VERIFIED (Phase 2)**
  - Measured: ROC-AUC=0.804, PR-AUC=0.178 (~5× random)
- **Model Evaluation + Explainability Foundation — IMPLEMENTED AND VERIFIED (Phase 3)**
  - Threshold calibration: XGBoost=0.80, IF=0.4679
  - CanonicalTransaction → IEEE-CIS feature mapper
  - Agent 1 ML scoring integration (`src/ml/agent1_scorer.py`)
  - 265 total tests
- **Agent 1 Anomaly Detector — IMPLEMENTED AND VERIFIED (Phase 4)**
  - `AnomalyDetectorAgent` — full processing flow (`src/agents/agent1/anomaly_detector.py`)
  - `Agent1Output` — validated Pydantic model (`src/agents/agent1/output_schema.py`)
  - SHAP per-prediction explanations; `combined_confidence` heuristic fusion
  - 54 new tests; 319 total tests passing
  - Git commit: `feat: implement agent 1 anomaly detector`
- **Mock Evidence Infrastructure — IMPLEMENTED AND VERIFIED (Phase 5)**
  - Centralised synthetic fixture registry (`src/evidence/fixture_data.py`)
  - Six deterministic mock providers: Core Banking, KYC, Device Registry, Beneficiary, Sanctions, Geolocation
  - NewsAPI provider interface with mock and live implementations
  - Shared Pydantic evidence response schema (`src/evidence/schemas.py`)
  - FastAPI application with 9 endpoints (`src/evidence/app.py`)
  - Cross-service consistency enforced at fixture level
  - 167 new tests; 486 total tests passing
  - `.env.example` created; credentials excluded from Git
  - Dependencies updated: fastapi, httpx, uvicorn, python-dotenv, pytest-asyncio
  - Git branch: `feature/mock-evidence-apis`
  - Git commit: `feat: add mock evidence services`

## Full-Dataset Evaluation Status

- Model artifacts from 15% stratified IEEE-CIS sample.
- Full training requires ≥16 GB RAM; current host has ~14 GB total.
- Training scripts support full-dataset runs (`sample_frac=None`).

## Next Major Milestones (Phase 6 and Beyond)

1. **Phase 6: Agent 2 (Evidence Gatherer)**
   - Orchestrate all seven providers in parallel
   - Aggregate into `Agent2Output` Pydantic model
   - Wire into LangGraph state graph alongside Agent 1
2. **LangGraph installation and node wiring**
   - Connect `AnomalyDetectorAgent` to LangGraph state
   - Wire Agent 2 as the second LangGraph node
3. **FastAPI ingestion endpoint** — accept raw transaction, invoke Agent 1 + Agent 2
4. **Agent 3 (Network Analyser)** — Neo4j graph analysis
5. **Agent 4 (Risk Assessor)**
6. **Agent 5 (Explanation Generator)** — Groq LLM
7. **Output Validator**
8. **MongoDB persistence** — case state
9. **Investigation Dashboard**

## Current Blockers

None. LangGraph is not installed — Agent 1 and evidence providers are ready for wiring
when LangGraph is added to the stack.

## Important Rule

Update this document whenever the active development phase changes.