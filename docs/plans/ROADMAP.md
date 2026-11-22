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
| 9 | Agent 4 Risk Assessor (config + mapping 1.0.0 approved 2026-11-21) |
| 9.5 | Investigation data coherence & hardening (see below) |
| 10 | Agent 5 Explanation Generator (see below) |
| 11 | Output Validator (see below) |

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

## Phase 10 — Agent 5 Explanation Generator (COMPLETE)

Details: `docs/02_AGENTS/AGENT_5_EXPLANATION_GENERATOR.md`.
1. **Evidence bundle.** A deterministic builder produces numbered, sourced
   facts (`F-001` …), formatted once, with `Not identified` for missing data,
   a bundle hash, and the label firewall applied again.
2. **LLM narrative.** Groq `openai/gpt-oss-120b`, strict JSON-schema output.
   It writes the narrative for Case Summary, Anomaly Findings, Evidence
   Summary, Network Analysis and Recommended Action. Every statement cites
   facts, and the output is checked structurally.
3. **Deterministic content.** The decision block, Regulatory Assessment and
   Source Audit Trail are written by code. The decision is copied from
   Agent 4.
4. **Template fallback.** Used when no LLM is configured or on any LLM
   failure, so the pipeline never blocks.

Added during Phase 10:
- India store masks `account_type = MULE_SUSPECT` (a ground-truth marker).
- Agent 3 reports PARTIAL when the graph holds < `min_graph_transfers`
  transfers (empty / unloaded graph is not a clean result).

## Phase 11 — Output Validator (COMPLETE)

Implemented as designed below. Details, grounding rules, fallback policy and
evaluation: `docs/02_AGENTS/OUTPUT_VALIDATOR.md`.
- The fallback decision was taken. When an LLM report fails, a template
  report built from the same bundle is validated and presented. The failed
  LLM report is kept in `rejected_reports` with its checks. If both fail,
  the case is NEEDS_HUMAN_REVIEW.
- Added to support validation: entity ids in evidence-fact labels;
  identifier / action citation completion in Agent 5 (recorded in
  `added_fact_ids`, never applied to numbers or dates); prompt 1.1.0;
  prompt size control and an adaptive completion budget for Groq's free tier.
- Result: 148 / 148 template reports and 6 / 6 LLM reports VALIDATED.

Original design:

Deterministic checks of `agent5_output` against its evidence bundle and
Agent 4. Result `VALIDATED` or `NEEDS_HUMAN_REVIEW`, with per-check results
kept on the case.

1. **Structure.** Seven sections in order, each non-empty. Every statement
   cites at least one fact id that exists in the bundle.
2. **Citation grounding.** Every amount, number, date/time and identifier
   (CASE-, TXN_, ACC_, CUST_, DEV_, rule ids) in a statement must appear in a
   fact that the statement cites. Normalise before comparing (thousands
   separators, `273` = `273.0`, date formats). Extract identifiers before
   numbers, so the digits inside an id are not treated as amounts. Phase 10
   produced a real failure of this kind: a correct date cited against facts
   that do not contain it.
3. **Decision consistency.** `decision` equals Agent 4. The SYSTEM decision
   statement matches it. An action name in LLM text must appear in a cited
   fact.
4. **Regulatory.** Referenced ids ⊆ Agent 4 regulatory matches. LLM
   statements name no regulator or regulation (FATF, RBI, PMLA, FIU,
   "Recommendation n").
5. **Language.** No conclusive wording in LLM text ("confirmed fraud",
   "is a money mule", "proves", "laundered" …). LLM statements about SAR/STR
   must not contradict `decision.sar_recommended`, e.g. negated SAR wording
   when a SAR is recommended.
6. **Leakage.** No dataset label strings (FRAUDULENT, LEGITIMATE,
   BORDERLINE, SCENARIO_, MULE_SUSPECT).
7. **Integrity.** The bundle hash recomputes. Every fact has a source. The
   audit trail cites every fact.

Decide in Phase 11: when an LLM report fails, also validate the template
report for the same bundle and present it, keeping the failed LLM report and
its check results for audit. Meaning-level misreadings (e.g. "average debit"
described as the average of all transactions) cannot be detected
deterministically and remain an analyst-review item.

## Phase 12 — LangGraph Orchestration (COMPLETE 2026-11-22)

- `src/agents/pipeline_graph.py`: `StateGraph(SentinelState)`, Agents 1–5 →
  Output Validator → finalise. `Investigator` (and so `run_investigation.py`
  and `evaluate_pipeline.py`) runs the compiled graph.
- Node wrapper enforces the handoffs: owned fields only, typed outputs,
  exceptions recorded in `pipeline_trace` (type only).
- Error edge: no risk score from Agent 4 → `halt_for_review` (no report,
  `HALTED`). Other node failures → `DEGRADED`, and downstream agents treat the
  missing output as unavailable.
- Equivalence: 72 cases on AuraDB give identical results to the sequential
  runner. Spec: `docs/09_BACKEND/LANGGRAPH_PIPELINE.md`.
- Backlog from Phase 11 (still open): on a paid LLM tier, ask the LLM once to
  repair a failed report using the validator's issues before falling back to
  the template report.

## Phase 13 — Ingestion API & Case Store (COMPLETE 2026-11-22)

- `src/api/`: FastAPI alert ingestion (full transaction, or a synthetic-feed
  transaction id), case queue in priority order, case detail, report
  (JSON / Markdown), audit trail, analyst decisions (revisable, all kept).
- Case store interface: JSON files (development) and MongoDB Atlas (hosted);
  conditional updates and an append-only audit trail. Both backends pass the
  same tests, including live tests on Atlas.
- One in-process investigation worker. Unfinished cases are queued again at
  restart. Peak memory 445 MB (Render 512 MB).
- CORS allow-list from env; `/health`; optional ingest API key.
- Spec: `docs/09_BACKEND/API_DESIGN.md`.
- Phase 13.1 (2026-11-22, requested by the project owner): analyst sign-in.
  Administrator-created accounts, scrypt passwords, server-side sessions in
  an HttpOnly cookie (7 days idle / 30 days max), lockout, revocation. The
  decision identity comes from the session. Phase 14 must call the API
  through a Vercel rewrite so the cookie is first-party.

## Phase 14 — Analyst Dashboard & Demonstration (COMPLETE 2026-11-22)

- `frontend/`: React 19 + TypeScript + Vite dashboard. Sign-in, priority
  queue, case detail (report with clickable fact citations and validator
  results, evidence with sources, network graph via React Force Graph, risk
  breakdown, audit trail, pipeline trace), and the analyst action panel.
- `GET /api/v1/cases/{id}/network`: graph built from the stored Agent 3
  findings only.
- `scripts/seed_demo_cases.py`: 2 fraudulent, 2 legitimate, 1 borderline,
  seed 14. Result: both fraud cases ESCALATE, both legitimate CLEAR, and the
  borderline case CLEAR at 24.30, just below MONITOR. All reports VALIDATED.
- Spec and results: `docs/10_FRONTEND/DASHBOARD.md`.

## Phase 15 — Deployment (Vercel + Render) (NEXT)

Design and constraints: `docs/14_OPERATIONS/DEPLOYMENT.md`.
- Render web service: build = `pip install -r requirements.txt && python scripts/build_artifacts.py`.
- Neo4j AuraDB Free (graph loaded once from a developer machine).
- Vercel static frontend; API base URL via env; no secrets on Vercel.
- Case store database (MongoDB Atlas M0 recommended).

Already in place (2026-11-21): env-only configuration, `neo4j+s://` support,
reproducible artifact build (`scripts/build_artifacts.py`), Agent 1 runs
without IEEE-CIS models (`SENTINEL_REQUIRE_IEEE_MODELS=false`),
`.python-version`.

## Decisions taken 2026-11-21 (delegated by the project owner)

- Agent 4 config 1.0.0 approved for the synthetic prototype. Weights and bands
  unchanged; added OVR-HIGH-ANOMALY (ANOMALY ≥ 0.70 → HUMAN_REVIEW, no SAR)
  so high-value spikes reach an analyst.
- Regulatory mapping 1.0.0: RBI references from the withdrawn PDF are
  SOURCE_WITHDRAWN and are never attached to a case. FATF references stay
  active and are labelled UNVERIFIED.

## Backlog / decisions outstanding

- Add the current RBI direction and PMLA / FIU-IND sources (PDFs) so India
  mappings can be restored; qualified review of FATF mappings.
- Re-approve Agent 4 configuration before any use on real data.
- Screening against the real OFAC SDN / UN consolidated list snapshots already
  in `dataset/raw/sanctions/` (currently only a synthetic watchlist is used).
- Full-dataset IEEE-CIS retraining on a host with ≥16 GB free RAM.
- Restore MongoDB Atlas.
