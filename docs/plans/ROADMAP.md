# Sentinel AI Roadmap

Phase numbering follows `docs/plans/CURRENT.md`.

## Phase 1 — Canonical Transaction Schema & Adapters (COMPLETE)

- `CanonicalTransaction` (Pydantic v2); IEEE-CIS, PaySim, India Synthetic adapters

## Phase 2 — ML Pipeline: XGBoost & Isolation Forest (COMPLETE)

- Loader, preprocessing, XGBoost classifier, Isolation Forest, SHAP

## Phase 3 — Model Evaluation & Explainability (COMPLETE)

- Metrics suite, threshold calibration, canonical → feature mapping, Agent 1 scorer

## Phase 4 — Agent 1 Anomaly Detector (COMPLETE)

- `AnomalyDetectorAgent`, combined_confidence (70/30), SHAP deviation features

## Phase 5 — Mock Evidence Infrastructure (COMPLETE)

- Core banking, KYC, device, beneficiary, sanctions, geolocation, news (mock + NewsAPI)

## Phase 6 — Agent 2 Evidence Gatherer (COMPLETE)

- Concurrent provider gather with provenance; `SentinelState`

## Phase 7 — Neo4j Graph Infrastructure (COMPLETE)

- Connection managers, schema, idempotent loader, query helper

## Phase 8 — Agent 3 Network Analyser (COMPLETE)

- Layering, structuring, fan-in, fan-out, mule-like, rapid forwarding, clusters

## Phase 9 — Agent 4 Risk Assessor (COMPLETE — config & mappings pending approval)

- Deterministic weighted scoring, action bands and overrides, SAR/STR recommendation
- Regulatory mapping registry (FATF / RBI, verbatim, UNVERIFIED)

## Phase 10 — Agent 5 Explanation Generator (NEXT)

- Groq LLM report from structured Agent 1–4 outputs only, following the report template
- Every factual claim traceable to a structured source field

## Phase 11 — Output Validator

- Deterministic checks of the generated report against source data
- Failed validation → flagged for human review

## Phase 12 — LangGraph Orchestration

- `StateGraph(SentinelState)` from alert to validated report

## Phase 13 — Ingestion API & Persistence

- FastAPI case ingestion; MongoDB case storage and analyst audit trail

## Phase 14 — Analyst Dashboard & Demonstration

- React analyst interface, network visualisation (React Force Graph)
- Five-case end-to-end demonstration (2 fraud, 2 legitimate, 1 borderline)
