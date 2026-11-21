# Agent 4 — Risk Assessor

## Status

IMPLEMENTED (Phase 9). Scoring configuration and regulatory mappings are
**PROPOSED — pending project team approval** (see "Approval status" below).

## Purpose

Combine outputs from the preceding investigation stages into a deterministic,
reproducible risk assessment. No LLM is involved.

## Code

| Module | Responsibility |
|---|---|
| `src/agents/agent4/config.py` | `Agent4Config`: weights, action bands, override switches, signal parameters |
| `src/agents/agent4/signals.py` | Extracts the seven signals from transaction + Agent 1/2/3 outputs |
| `src/agents/agent4/regulatory_mapping.py` | Approved-source regulatory reference registry |
| `src/agents/agent4/output_schema.py` | `Agent4Output` and sub-models (frozen Pydantic) |
| `src/agents/agent4/risk_assessor.py` | `RiskAssessorAgent`: LangGraph-compatible node |
| `tests/test_agent4_risk_assessor.py` | 112 tests |

## Inputs

From `SentinelState`:

- `transaction` (required)
- `agent1_output` (falls back to `agent2_output.agent1_output`)
- `agent2_output`
- `agent3_output`

Any upstream output may be missing or failed; Agent 4 still produces an output.

## Risk Signals

| Signal | Sources (max of available indicators) |
|---|---|
| ANOMALY | Agent 1 `combined_confidence`, else XGBoost `anomaly_score` |
| NEW_DEVICE | `transaction.device.is_new_device`; device registry registration / NOT_FOUND |
| NEW_BENEFICIARY | `transaction.metadata.is_new_beneficiary`; beneficiary DB (prior-fraud flag, zero history, account age); sender's known beneficiaries (core banking) |
| UNUSUAL_TIMING | local hour in night window; payment soon after beneficiary was added |
| NETWORK_RISK | max `heuristic_score` of Agent 3 findings |
| SANCTIONS_HIT | sanctions subject / account screens |
| LOCATION_ANOMALY | geolocation `is_anomalous` |

Each signal is a value in [0, 1] or **UNAVAILABLE**. Unavailable evidence is
never scored as 0 ("safe"): Agent 3 `UNAVAILABLE`/`FAILED`, a `PARTIAL` run
with no findings, failed providers, and missing coordinates are all
unavailable.

Weights, bands and thresholds are documented in
`docs/07_RISK_AND_COMPLIANCE/RISK_SCORING.md`.

## Output (`Agent4Output`)

- `risk_score` (0–100) and `score_band_action`
- `score_breakdown`: per signal — weight, availability, value, contribution,
  rationale, and `evidence_refs` (source agent, provider, MOCK/LIVE, request /
  finding id, timestamp)
- `evidence_coverage` and `unavailable_signals`
- `recommended_action` (CLEAR / MONITOR / HUMAN_REVIEW / ESCALATE / BLOCK)
- `overrides_applied` (rule ids)
- `confidence` (HIGH / MEDIUM / LOW) with `confidence_reasons`
- `sar_recommendation` (system recommendation only; basis rule ids)
- `regulatory_matches` and `unmapped_triggers`
- `config_version`, `config_approval_status`, `config_snapshot`, `mapping_version`
- upstream run ids and statuses
- `status`: COMPLETE / PARTIAL / FAILED / VALIDATION_ERROR

Reproducibility: `risk_score = 100 × Σ contribution / evidence_coverage`.

## Failure behaviour

| Situation | Result |
|---|---|
| No transaction | `VALIDATION_ERROR`, action HUMAN_REVIEW, no score |
| No signal available | `FAILED`, action HUMAN_REVIEW, no score |
| Internal exception | `FAILED`, HUMAN_REVIEW, sanitised error (type name only) |
| Some signals unavailable | `PARTIAL`, score over available weight, lower confidence |

## Regulatory Mapping

Triggers are derived from signals (≥ `trigger_threshold`), KYC evidence
(not VERIFIED, PEP), Agent 3 pattern types, sanctions matches and the SAR
recommendation. They are resolved **only** against
`regulatory_mapping.py`. Triggers with no approved entry are listed in
`unmapped_triggers`; nothing is invented. See
`docs/07_RISK_AND_COMPLIANCE/REGULATORY_MAPPING.md`.

## Approval status

The project plan referenced a weighted model but no weights were recorded in
the repository. The Phase 9 values are proposed defaults; every output is
stamped `config_version = 0.1.0-proposed` and
`config_approval_status = PROPOSED — pending project team approval`. Once the
team approves (or changes) the values, update `Agent4Config`, bump
`config_version`, set the approval status, and record the change here.

## Important Rules

- The LLM must not compute or change the score, weights, thresholds, actions
  or regulatory mappings. Agent 5 may only explain them.
- A SAR/STR recommendation is not a filing and requires qualified human review.
