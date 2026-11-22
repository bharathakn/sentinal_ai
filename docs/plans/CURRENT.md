# Current Project State

## Project

Sentinel AI

## Current Phase

| Phase | Status |
|---|---|
| 1 — Canonical schema & adapters | COMPLETE |
| 2 — ML pipeline (XGBoost + Isolation Forest) | COMPLETE |
| 3 — Evaluation & explainability | COMPLETE |
| 4 — Agent 1 Anomaly Detector | COMPLETE |
| 5 — Mock evidence infrastructure | COMPLETE |
| 6 — Agent 2 Evidence Gatherer | COMPLETE |
| 7 — Neo4j graph infrastructure | COMPLETE |
| 8 — Agent 3 Network Analyser | COMPLETE (rules superseded by v2 in 9.5) |
| 9 — Agent 4 Risk Assessor | COMPLETE (config + mapping 1.0.0 approved) |
| 9.5 — Investigation data coherence & hardening | COMPLETE |
| 10 — Agent 5 Explanation Generator | COMPLETE |
| 11 — Output Validator | COMPLETE |
| 12 — LangGraph orchestration | COMPLETE |
| 13 — Ingestion API & case store | COMPLETE |
| 14 — Analyst dashboard & demonstration | COMPLETE |
| **15 — Deployment (Vercel + Render)** | **IN PROGRESS** — prepared and rehearsed; owner reviewing the local preview |

See `docs/plans/ROADMAP.md` for the plan and the reasons it changed.

## Current Objective

Phase 15: the dashboard was redesigned at the project owner's request
(upload or demo → five live animated agents → final report → resolve) and
awaits their review on localhost. Nothing is deployed. Fixed 2026-11-22: the
alert-endpoint graph write and Agent 3's cycle limit. The rehearsal under
Render Free limits passed on 2026-11-22; the project owner deploys with the
runbook in `docs/14_OPERATIONS/DEPLOYMENT.md`.

Phase 15: deployment is prepared (`render.yaml`, `frontend/vercel.json`,
runbook in `docs/14_OPERATIONS/DEPLOYMENT.md`) and rehearsed from a clean
copy. The project owner is reviewing the dashboard on localhost before
deployment.

Phase 14 complete: React analyst dashboard (`frontend/`) on the Phase 13 API,
plus the five-case demonstration (`scripts/seed_demo_cases.py`). Checked in
headless Chrome against the real API. Next: Phase 15, deployment on Vercel
(`frontend/`, rewrite `/api` to Render) and Render (API), with Atlas and
AuraDB.

Phase 13 complete: FastAPI investigation API (`src/api/`). Alerts create
cases, which are investigated on one background worker and stored in a case
store: JSON files locally, MongoDB Atlas when hosted. Analysts read the
priority queue, case detail, report and audit trail, and record decisions,
which are revisable and audited. Analysts sign in (Phase 13.1) and stay
signed in for up to 30 days. Verified end to end on AuraDB + Atlas.
Next: Phase 14, the React analyst dashboard.

Phase 12 complete: the investigation runs as a LangGraph `StateGraph`
(`src/agents/pipeline_graph.py`). Every node may write only its own typed
output and is recorded in `pipeline_trace`. If Agent 4 produces no risk
score, the case halts for human review without a report. Other node failures
mark the case `DEGRADED`. Results are identical to the old sequential runner
(72 cases on AuraDB). Next: Phase 13, ingestion API + MongoDB case store.

Phase 11 complete: every report is checked by a deterministic Output
Validator (7 checks). Only VALIDATED reports are presented as validated; a
failed LLM report is replaced by a validated template report built from the
same evidence, and the failed one is kept for audit. Evaluation: 148/148
template and 6/6 LLM reports VALIDATED. Next: Phase 12, LangGraph.

Phase 10: Agents 1–5 run end to end. Each case ends with a seven-section
draft report in which every statement cites numbered evidence facts. Groq
writes the narrative; the decision block, regulatory section and audit trail
are deterministic; a template writer is the fallback. Reports stay
`NOT_VALIDATED` until Phase 11. Next: Output Validator (design in
`docs/plans/ROADMAP.md`).

Phase 9.5: every agent works on one coherent investigation world (India
synthetic dataset v2).

End-to-end (Agents 1–4, 575 labelled cases, config 1.0.0): legitimate →
0% ESCALATE/BLOCK (0.3% HUMAN_REVIEW); fraudulent → 83% ESCALATE/BLOCK and
0% CLEAR. Details in `docs/07_RISK_AND_COMPLIANCE/RISK_SCORING.md`.

Deployment target (Vercel + Render) recorded in
`docs/14_OPERATIONS/DEPLOYMENT.md`; deploy-compatibility groundwork is done.

## Phase 14 summary

- Dashboard: sign-in, queue, case detail (report + citations + validation,
  evidence, network graph, audit trail, pipeline), risk panel, decision panel.
  Spec: `docs/10_FRONTEND/DASHBOARD.md`.
- Network endpoint from stored Agent 3 findings (`src/api/network_view.py`).
- Demo: 2 fraud → ESCALATE, 2 legitimate → CLEAR, borderline → CLEAR (24.30).
- Tests: `tests/test_network_view.py`; `frontend` Vitest (15).

## Phase 13.1 summary (analyst sign-in)

- `src/api/auth.py`: username/password sign-in; sessions last 7 days idle,
  30 days max, so analysts rarely sign in again. HttpOnly cookie; only the
  token hash is stored. 5-failure lockout. Sign-out, disable and password
  change revoke sessions.
- All case endpoints require sign-in. Decisions and ingestions are
  attributed to the signed-in user. Ingestion alternatively accepts the
  server-side ingest key.
- Accounts: `scripts/manage_users.py` (no public sign-up).
- Tests: `tests/test_auth.py` (+ MongoDB auth store live on Atlas).

## Phase 13 summary

- Endpoints: `/health`, `POST /api/v1/alerts`, `GET /api/v1/cases[/{id}[/report|/audit]]`,
  `POST /api/v1/cases/{id}/decision`. Server: `uvicorn src.api.main:app --workers 1`.
- Case lifecycle RECEIVED → INVESTIGATING → AWAITING_REVIEW → DECIDED
  (or INVESTIGATION_FAILED); duplicate alerts return the existing case; labels
  stripped before storage; only exception types stored.
- `SENTINEL_CASE_STORE=json|mongodb`; `pymongo` added to requirements.
- Tests: `tests/test_api.py` (store tests also live on Atlas, temporary DB).

## Phase 12 summary

- `build_investigation_graph(...)` compiles: anomaly_detector →
  evidence_gatherer → network_analyser → risk_assessor →
  (explanation_generator → output_validator | halt_for_review) → finalise.
- New state fields: `pipeline_trace`, `halt_reason`, `pipeline_status`
  (COMPLETE / DEGRADED / HALTED), `pipeline_version`, `case_completed_at_utc`.
- `run_investigation.py` prints the node trace; `langgraph>=1.2.0` added to
  requirements. LangSmith tracing must stay off (`LANGSMITH_TRACING=false`).
- Tests: `tests/test_pipeline_graph.py`.

## Phase 10 summary

- `src/agents/agent5/`: evidence bundle (`facts.py`), Groq client with strict
  JSON-schema output (`llm_client.py`), prompt + structural parser
  (`prompt.py`), template and SYSTEM writers (`writers.py`), agent
  (`explanation_generator.py`), Markdown rendering (`render.py`).
- `Investigator` runs Agent 5 (`generate_report=False` for bulk evaluation);
  `scripts/run_investigation.py` prints or writes the report.
- Fixes found while building it: India store masks the `MULE_SUSPECT` label;
  Agent 3 reports PARTIAL on an empty / unloaded graph; bulk graph loader
  (`load_batch_unwind`; full load into AuraDB in 8 s instead of ~1 h).
- Verified on AuraDB: 95-case sample gives identical Agent 4 results to the
  local graph. LLM reports produced for normal, layering, high-value spike,
  new-device and borderline-travel cases.

## Phase 9.5 summary

- **Dataset v2** (`src/data/synthetic_india_generator.py`): scenarios generated
  as real transaction patterns (chains, fan-in/out, cycles, bursts); entity
  tables consistent with transaction flags; features derived from the ledger;
  labels only in the targets file. Validator check 7 enforces consistency.
  v1 archived at `dataset/processed/_archive/custom_india_v1/`.
- **Evidence backend abstraction** (`src/evidence/data_store.py`): `fixture`
  (tests) / `india_synthetic` (point-in-time). Agent 2 screens the KYC name
  when the transaction has no sender name.
- **Agent 3 rules v2**: temporal, anchored on the investigated transaction,
  sender and receiver analysed. v1 flagged 100% of transactions on the full
  graph.
- **Agent 1 India-native model** (`src/ml/india_behaviour_model.py`):
  XGBoost test ROC-AUC 0.972 / PR-AUC 0.853 (synthetic labels).
- **Label firewall + case identity**: `new_case_state()`.
- **Runner / evaluation**: `scripts/run_investigation.py`,
  `scripts/evaluate_pipeline.py`, `src/agents/investigation.py`.
- **Agent 4 fix**: beneficiary's own transaction count no longer treated as a
  new-relationship signal.

## Environment (2026-11-21)

- Work is committed directly on `main`.
- Neo4j: `.env` now points to the project owner's AuraDB instance
  (changed 2026-11-21), loaded with all 10,000 v2 transactions. The local
  Docker container `sentinel-neo4j` still exists with its own copy of the graph.
- MongoDB Atlas: verified 2026-11-21 (MongoDB 8.0). Used by the Phase 13
  case store (`SENTINEL_CASE_STORE=mongodb`, database `sentinel_ai`). Network
  access allows the developer IP only; add Render's outbound IP ranges at
  deployment (see DEPLOYMENT.md).
- Groq and NewsAPI keys verified working.
- Rebuild sequence: generate dataset → train India model → load graph
  (see `docs/14_OPERATIONS/DEVELOPMENT_SETUP.md`).

## Decisions (2026-11-21, delegated by the project owner)

1. Agent 4 config 1.0.0: weights/bands kept; OVR-HIGH-ANOMALY added
   (ANOMALY ≥ 0.70 → HUMAN_REVIEW, no SAR).
2. Regulatory mapping 1.0.0: withdrawn RBI references inactive; FATF active
   (UNVERIFIED).

## Open items (project owner)

- Supply the current RBI direction and PMLA / FIU-IND PDFs to restore India
  mappings.
- Create the real analyst accounts on Atlas before the demo
  (`scripts/manage_users.py`, see `docs/14_OPERATIONS/DEPLOYMENT.md`).

## Known limitations

- Full IEEE-CIS retraining needs ≥ 16 GB free RAM (host has ~5 GB available).
- Sanctions screening uses a synthetic watchlist; real OFAC / UN snapshots are
  unused (backlog).
- ~32% of legitimate transactions get some network finding because they touch
  an account involved in a fraud pattern (intended counterparty context;
  weighed by Agent 4).

## Important Rule

Update this document whenever the active development phase changes.
