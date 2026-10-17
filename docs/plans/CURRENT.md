# FILE: docs/plans/CURRENT.md

# Current Project State

## Project

Sentinel AI

## Current Phase

- Phase 1 — Canonical Transaction Schema & Data Adapters: COMPLETE
- Phase 2 — ML Data Pipeline (XGBoost + Isolation Forest): COMPLETE
- Phase 3 — Model Evaluation + Explainability Foundation: COMPLETE
- Phase 4 — Agent 1 Anomaly Detector: COMPLETE
- Phase 5 — Mock Evidence Infrastructure: COMPLETE
- Phase 6 — Agent 2 Evidence Gatherer: COMPLETE
- Phase 7 — Neo4j Graph Infrastructure: COMPLETE
- Phase 8 — Agent 3 Network Analyser: COMPLETE

**Next Planned Phase**: Phase 9 — Agent 4 Risk Assessor (aggregate risk scoring
from Agent 1/2/3 outputs).

## Current Objective

Phase 8 complete. 739/739 tests passing (81 unit + 9 live integration for Agent 3;
full suite Phases 1–8 intact).

## Completed

- Project concept, five-agent architecture, and technology stack defined.
- Synthetic India Dataset generated and validated (SYNTHETIC DATA).
- **Phase 1**: `CanonicalTransaction` Pydantic model, three dataset adapters, 82 tests.
- **Phase 2**: XGBoost (ROC-AUC=0.934, PR-AUC=0.662) and Isolation Forest (ROC-AUC=0.804).
- **Phase 3**: Threshold calibration, feature mapper, model evaluation, 265 tests.
- **Phase 4**: `AnomalyDetectorAgent` — full scoring pipeline with SHAP, 319 tests.
  - Commit: `feat: implement agent 1 anomaly detector`
- **Phase 5**: Mock evidence infrastructure for 7 provider categories.
  - Centralised synthetic fixture registry. FastAPI app. 486 tests.
  - Commit: `feat: add mock evidence services`
- **Phase 6**: Agent 2 Evidence Gatherer.
  - `EvidenceGathererAgent` — asyncio concurrent 8-provider gather.
  - `Agent2Output` — structured, validated Pydantic output.
  - `SentinelState` TypedDict — LangGraph-compatible pipeline state.
  - 73 new tests; 559 total tests passing.
  - Branch: `feature/agent2-evidence-gatherer`
  - Commit: `feat: implement agent 2 evidence gathering`
- **Phase 7**: Neo4j Graph Infrastructure.
  - `Neo4jConnectionManager` — sync driver lifecycle, health check.
  - `AsyncNeo4jConnectionManager` — async driver for asyncio contexts.
  - `GraphSchemaManager` — idempotent constraint/index initialisation.
  - `TransactionGraphLoader` — idempotent MERGE-on-tx_graph_id loader.
  - `GraphQueryHelper` — parameterised account/transfer/path queries.
  - `mapping.py` — allowlisted property extraction and validation.
  - 70 unit tests (mocked) + 20 live integration tests (Neo4j AuraDB).
  - All 649 tests passing; Phases 1–6 fully intact.
  - Branch: `feature/neo4j-graph`
  - Commit: `feat: add Neo4j graph infrastructure`
- **Phase 8**: Agent 3 Network Analyser.
  - `NetworkAnalyserAgent` — LangGraph-compatible callable; analyses account network.
  - 7 pattern detectors: Layering, Structuring, Fan-in, Fan-out, Mule-like,
    Rapid Forwarding, Suspicious Cluster.
  - `Agent3Config` — centralised thresholds with env-var overrides and disclaimers.
  - `Agent3Output`, `NetworkFinding`, `LayeringPath`, `TransferRef` — typed, frozen schemas.
  - `SentinelState.agent3_output` — fully wired into pipeline state.
  - `docs/06_AGENT3/NETWORK_ANALYSER.md` — full detector documentation.
  - 81 unit tests (mocked) + 9 live Neo4j integration tests.
  - All 739 tests passing; Phases 1–7 fully intact.
  - Branch: `feature/agent3-network-analyser`
  - Commit: `feat: implement agent 3 network analyser`

## Next Major Milestones

1. **Phase 9: Agent 4 (Risk Assessor)** — aggregate risk scoring from Agent 1/2/3 outputs.
2. **Phase 10: Agent 5 (Explanation Generator)** — Groq LLM narrative.
3. **LangGraph installation** — wire agents into `StateGraph(SentinelState)`.
4. **MongoDB case persistence** — investigation case schema and storage.
5. **FastAPI ingestion endpoint** — accept raw transaction, run pipeline.
6. **Investigation Dashboard**.

## Current Blockers

- LangGraph not installed. `SentinelState` TypedDict is LangGraph-compatible;
  wiring into `StateGraph` deferred until LangGraph is added to the stack.
- Full-dataset XGBoost training requires ≥16 GB RAM (current host ~14 GB).

## Important Rule

Update this document whenever the active development phase changes.