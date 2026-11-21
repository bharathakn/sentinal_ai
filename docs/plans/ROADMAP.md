# Sentinel AI Roadmap

Phase numbering follows `docs/plans/CURRENT.md`. Revised 2026-11-21 after a
full project review (see "Why the plan changed").

## Completed

| Phase | Scope |
|---|---|
| 1 | Canonical transaction schema; IEEE-CIS, PaySim, India Synthetic adapters |
| 2 | XGBoost + Isolation Forest pipeline, SHAP |
| 3 | Evaluation, threshold calibration, canonical → feature mapping |
| 4 | Agent 1 Anomaly Detector |
| 5 | Mock evidence infrastructure (7 provider categories) |
| 6 | Agent 2 Evidence Gatherer |
| 7 | Neo4j graph infrastructure |
| 8 | Agent 3 Network Analyser |
| 9 | Agent 4 Risk Assessor (config + mappings pending approval) |
| 9.5 | Investigation data coherence & hardening (see below) |

## Why the plan changed

The review found that each agent was working on a different "world":

- Agent 1 scores with IEEE-CIS models. For India transactions ~430 of ~434
  features are imputed, so the score is near-constant (0.219 for both a
  normal and a suspicious case in the Phase 9 smoke run).
- Agent 2's mock evidence only knows four hand-written accounts (ACC001–004).
- Agent 3's graph held 500 of the 10,000 India transactions.

So no single case could receive meaningful output from every agent, and the
planned five-case demonstration could not work. Phase 9.5 makes the India
synthetic dataset the one coherent investigation world. Phases 10–11 were
redesigned so that the LLM report is mechanically verifiable.

## Phase 9.5 — Investigation Data Coherence & Hardening (COMPLETE)

1. **Evidence backend abstraction.** Providers read from a pluggable store:
   `fixture` (unit tests, default) or `india_synthetic` (customers, accounts,
   devices, beneficiaries, transaction history from
   `dataset/processed/custom_india/`). Selected by `SENTINEL_EVIDENCE_BACKEND`.
2. **Sanctions name screening fallback.** When the transaction carries no
   sender name, Agent 2 screens the KYC customer name.
3. **Full India graph load.** All 10,000 transactions in Neo4j.
3a. **Dataset v2** (added during 9.5). The review found v1's network scenarios
   had no network structure (sender/receiver drawn at random) and its entity
   tables contradicted the transaction flags. The generator was rebuilt so
   scenarios are real transaction patterns and all features are derived.
3b. **Agent 3 rules v2** (added during 9.5). With the full graph loaded, v1's
   timeless rules flagged 100% of transactions. v2 rules are temporal and
   anchored on the investigated transaction.
4. **India-native Agent 1 model.** XGBoost + Isolation Forest + SHAP trained
   on behavioural features extracted from `CanonicalTransaction` (same code
   path for training and scoring). Agent 1 routes India transactions to it and
   keeps the IEEE-CIS models for IEEE-CIS data. Features that Agent 4 already
   scores as separate signals (new device, new beneficiary, distance from
   home, beneficiary-added timing) are excluded to avoid double counting.
5. **Label firewall.** Ground-truth fields (`is_fraud`, `risk_label`,
   `scenario_id`) are stripped from the transaction before any agent sees it.
   They are used only by evaluation code.
6. **Case identity.** `SentinelState` carries `case_id` and
   `case_created_at_utc` (needed by the report's Case Summary).
7. **Investigation runner.** `scripts/run_investigation.py <transaction_id>`
   runs the pipeline on one India transaction and prints the outcome.
8. **Agent 4 policy evaluation.** Run Agents 1–4 over the labelled India
   alerts and a legitimate sample; publish the action-versus-label table as
   evidence for approving (or changing) the proposed weights. No silent tuning.

## Phase 10 — Agent 5 Explanation Generator (NEXT)

1. **Evidence bundle.** A deterministic builder turns the case state into a
   flat list of facts, each with a stable id (`F-001` …), value, source agent,
   source field path, source mode and timestamp. Label fields never enter it.
2. **Structured generation.** The Groq LLM returns JSON: the seven report
   sections, each a list of statements, and every statement cites fact ids.
   The LLM writes prose only; score, action, SAR recommendation and regulatory
   references are copied from Agent 4, never decided by the LLM.
3. **Template fallback.** If no API key is configured, the call fails, or the
   output cannot be parsed, a deterministic template writer produces the same
   structure (`generator = TEMPLATE`). The pipeline never blocks on the LLM.
4. Missing data rendered as `Not identified`.

## Phase 11 — Output Validator

Deterministic checks against the evidence bundle:
- every statement cites ≥1 existing fact id
- every amount, date/time, account / customer / device id in the text appears
  in a cited fact
- regulatory references ⊆ Agent 4 regulatory matches
- recommended action and SAR recommendation equal Agent 4's
- all seven sections present; no label leakage

Result `VALIDATED` or `NEEDS_HUMAN_REVIEW`, with per-check results.

## Phase 12 — LangGraph Orchestration

- `StateGraph(SentinelState)`: Agents 1–5 → Output Validator, with error edges.
- `run_investigation.py` switches to the graph.

## Phase 13 — Ingestion API & Case Store

- FastAPI: alert ingestion (case id), case retrieval, analyst decision + audit trail.
- Case store behind an interface: local JSON store for development; MongoDB
  Atlas adapter once the cluster is restored (deferred by the project owner).

## Phase 14 — Analyst Dashboard & Demonstration

- React analyst UI, network visualisation (React Force Graph).
- Five-case demonstration drawn from labelled India scenarios
  (2 fraudulent, 2 legitimate, 1 borderline).

## Backlog / decisions outstanding

- Approve Agent 4 weights, bands, overrides (`config_version 0.1.0-proposed`).
- Verify regulatory mappings; replace the withdrawn RBI direction; add
  PMLA / FIU-IND sources.
- Screening against the real OFAC SDN / UN consolidated list snapshots already
  in `dataset/raw/sanctions/` (currently only a synthetic watchlist is used).
- Full-dataset IEEE-CIS retraining on a host with ≥16 GB free RAM.
- Restore MongoDB Atlas.
