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
| 9 — Agent 4 Risk Assessor | COMPLETE (config + mappings PROPOSED, pending approval) |
| 9.5 — Investigation data coherence & hardening | COMPLETE |
| **10 — Agent 5 Explanation Generator** | **NEXT** |

See `docs/plans/ROADMAP.md` for the plan and the reasons it changed.

## Current Objective

Phase 9.5 complete: every agent now works on one coherent investigation world
(India synthetic dataset v2). 897/897 tests passing, 0 skipped (live Neo4j
tests run against the local Docker instance).

End-to-end (Agents 1–4, 575 labelled cases, proposed config): legitimate →
0% ESCALATE/BLOCK; fraudulent → 83% ESCALATE/BLOCK. Details in
`docs/07_RISK_AND_COMPLIANCE/RISK_SCORING.md`.

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
- Neo4j: local Docker container `sentinel-neo4j` (bolt://localhost:7687,
  volume `sentinel_neo4j_data`), loaded with all 10,000 v2 transactions.
- MongoDB Atlas: cluster in `MONGODB_URI` no longer resolves. Deferred by the
  project owner.
- Groq and NewsAPI keys verified working.
- Rebuild sequence: generate dataset → train India model → load graph
  (see `docs/14_OPERATIONS/DEVELOPMENT_SETUP.md`).

## Decisions outstanding (project owner)

1. Approve or change Agent 4 weights / bands / overrides
   (`config_version 0.1.0-proposed`). Notably: should a high-value spike alone
   escalate?
2. Verify the regulatory mappings (all UNVERIFIED). The RBI Fraud Risk
   Management PDF carries a "Withdrawn" watermark; supply the current direction
   and PMLA / FIU-IND sources if they should be mapped.

## Known limitations

- Full IEEE-CIS retraining needs ≥ 16 GB free RAM (host has ~5 GB available).
- Sanctions screening uses a synthetic watchlist; real OFAC / UN snapshots are
  unused (backlog).
- ~32% of legitimate transactions get some network finding because they touch
  an account involved in a fraud pattern (intended counterparty context;
  weighed by Agent 4).

## Important Rule

Update this document whenever the active development phase changes.
