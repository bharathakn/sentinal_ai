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
- Phase 9 — Agent 4 Risk Assessor: COMPLETE (scoring config + regulatory
  mappings PROPOSED, pending team approval)

**Next Planned Phase**: Phase 10 — Agent 5 Explanation Generator (Groq LLM
narrative grounded only in structured Agent 1–4 outputs).

## Current Objective

Phase 9 complete. 851/851 tests passing, 0 skipped (live Neo4j integration
tests now run against the local Docker instance).

Approvals outstanding (human action):
- Agent 4 weights / bands / overrides (`Agent4Config`, version 0.1.0-proposed).
- Regulatory mapping entries (all UNVERIFIED). The RBI Fraud Risk Management
  PDF in the repo carries a "Withdrawn" watermark; confirm the current direction.

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

- **Phase 9**: Agent 4 Risk Assessor.
  - `RiskAssessorAgent` — deterministic weighted scoring over 7 signals; no LLM.
  - Unavailable evidence lowers `evidence_coverage`; never scored as safe.
  - Action bands + overrides (sanctions match → BLOCK; sanctions failure / low
    coverage → HUMAN_REVIEW); SAR/STR recommendation as system recommendation only.
  - Regulatory registry: 10 verbatim FATF/RBI references, 18 mappings, all
    UNVERIFIED; unmapped triggers reported, never invented.
  - `SentinelState.agent4_output` wired. 112 new tests.
  - Docs: `docs/02_AGENTS/AGENT_4_RISK_ASSESSOR.md`,
    `docs/07_RISK_AND_COMPLIANCE/RISK_SCORING.md`, `REGULATORY_MAPPING.md`.

## Environment (2026-11-21)

- Work is committed directly on `main`; feature branches were merged and removed.
- Neo4j: local Docker container `sentinel-neo4j` (bolt://localhost:7687,
  volume `sentinel_neo4j_data`). The former AuraDB instance no longer exists.
  Sample graph: `PYTHONPATH=. python scripts/load_india_sample_graph.py`.
- `tests/conftest.py` loads only `NEO4J_*` keys from `.env`.
- MongoDB Atlas: the cluster in `MONGODB_URI` no longer resolves; needs
  recreating before the persistence phase.
- Groq and NewsAPI keys verified working.

## Next Major Milestones

1. **Phase 10: Agent 5 (Explanation Generator)** — Groq LLM narrative.
2. **Phase 11: Output Validator** — deterministic report validation.
3. **Phase 12: LangGraph orchestration** — `StateGraph(SentinelState)` end to end.
4. **Phase 13: FastAPI ingestion + MongoDB case persistence / audit trail**.
5. **Phase 14: Investigation Dashboard** and five-case demonstration.

## Current Blockers

- LangGraph not installed. `SentinelState` TypedDict is LangGraph-compatible;
  wiring into `StateGraph` deferred until LangGraph is added to the stack.
- Full-dataset XGBoost training requires ≥16 GB RAM (current host ~14 GB).
- Agent 1 scores non-IEEE-CIS transactions in CANONICAL_MAPPED mode with most
  features imputed (COMPATIBILITY_WARNING); its score is near-constant for
  mock / India-synthetic cases.

## Important Rule

Update this document whenever the active development phase changes.