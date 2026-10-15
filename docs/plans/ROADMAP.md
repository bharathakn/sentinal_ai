# FILE: docs/plans/ROADMAP.md

# Sentinel AI Roadmap

## Phase 1 — Canonical Transaction Schema & Adapters (COMPLETE & VERIFIED)

- Canonical transaction model (`CanonicalTransaction` via Pydantic v2)
- IEEE-CIS, PaySim, and India Synthetic adapters
- Unit test suite (82 tests passing)
- Schema documentation and provenance enforcement

## Phase 2 — ML Data Pipeline: XGBoost & Isolation Forest (COMPLETE & VERIFIED)

- Dataset loader & feature engineering pipeline
- Supervised fraud classifier (XGBoost) with class-imbalance weighting
- Unsupervised anomaly detector (Isolation Forest)
- SHAP feature explainability layer
- Model artifact persistence and prediction consistency tests (117 tests passing)

## Phase 3 — Model Evaluation & Explainability Foundation (COMPLETE & VERIFIED)

- Evaluator metrics suite (Accuracy, Precision, Recall, F1, ROC-AUC, PR-AUC, FPR, FNR, Confusion Matrix)
- Threshold calibration with strict test-set isolation
- CanonicalTransaction → model feature mapping (`src/ml/feature_mapper.py`)
- Standalone Agent 1 ML scoring engine (`src/ml/agent1_scorer.py`)
- Full-dataset readiness and configuration verification
- Total automated tests: 265 passing

## Phase 4 — Agent 1 Anomaly Detector (NEXT PLANNED PHASE — NEXT WEEK)

- Agent 1 LangGraph node definition and state integration
- Score fusion strategy (`combined_confidence`)
- Structured Agent 1 output (`anomaly_score`, `isolation_score`, `combined_confidence`, `top_deviation_features`)
- Agent scenario tests (normal, suspicious, malformed, sparse input, model unavailable)

## Phase 5 — Evidence Gathering & Connectors (Agent 2)

- Mock banking APIs (Core Banking, KYC, Device Registry, Beneficiary DB, Geolocation)
- Public news search integration
- Evidence provenance and timestamp tracking

## Phase 6 — Graph Database & Network Analysis (Agent 3)

- Neo4j graph schema setup and transaction ingestion
- Circular transaction flow and fan-out/fan-in detection
- Suspicious community and mule account identification

## Phase 7 — Risk Assessment (Agent 4) & Explanation (Agent 5)

- Regulatory rule mapping (RBI, FATF, OFAC, UN sanctions)
- Weighted multi-dimensional risk scoring
- LLM grounded narrative explanation via Groq API

## Phase 8 — Deterministic Output Validation & Pipeline Wiring

- Rule-based fact-checking and hallucination prevention (Output Validator)
- Multi-agent LangGraph orchestration from alert to validated report

## Phase 9 — Storage & Ingestion API

- FastAPI case ingestion endpoints
- MongoDB Atlas case and audit log persistence

## Phase 10 — Analyst Dashboard & Demonstration

- React compliance analyst interface
- Network visualization (React Force Graph)
- Five-case end-to-end demonstration (2 fraud, 2 legitimate, 1 borderline)