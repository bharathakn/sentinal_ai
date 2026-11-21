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
| **11 — Output Validator** | **NEXT** |

See `docs/plans/ROADMAP.md` for the plan and the reasons it changed.

## Current Objective

Phase 10 complete: Agents 1–5 run end to end. Each case ends with a seven-section
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
- MongoDB Atlas: new cluster configured and verified 2026-11-21 (ping,
  write, read, delete; MongoDB 8.0). Network access allows the developer IP
  only; Render will need `0.0.0.0/0` or equivalent at deployment. Not yet
  used by code: the case store arrives in Phase 13 (add `pymongo` to
  requirements then).
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
- Case store for the hosted deployment (Render disk is ephemeral): MongoDB
  Atlas, now available (Phase 13).

## Known limitations

- Full IEEE-CIS retraining needs ≥ 16 GB free RAM (host has ~5 GB available).
- Sanctions screening uses a synthetic watchlist; real OFAC / UN snapshots are
  unused (backlog).
- ~32% of legitimate transactions get some network finding because they touch
  an account involved in a fraud pattern (intended counterparty context;
  weighed by Agent 4).

## Important Rule

Update this document whenever the active development phase changes.
