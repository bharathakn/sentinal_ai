# FILE: docs/09_BACKEND/API_DESIGN.md

# API Design

## Purpose

Define the backend API boundary for Sentinel AI.

## Primary Entry Point

FastAPI.

## Alert Ingestion

The system requires an endpoint for receiving suspicious transaction alerts.

The alert contains the transaction information needed to create a case.

## Case

The backend must expose the information required by the dashboard to display:

- case information
- investigation status
- risk score
- evidence
- network findings
- report
- validation
- recommended action

## Analyst Action

The backend must accept analyst decisions from the dashboard and preserve the associated audit information.

## API Principle

API contracts should use structured validation.

Pydantic is the project's validation technology.

## Implementation (Phase 13)

IMPLEMENTED. Code: `src/api/` (`app.py` routes, `service.py` case service,
`case_store.py` stores, `case_schema.py` models, `main.py` server entry).
API version `1.0.0`; case schema `1.0.0`.

```bash
uvicorn src.api.main:app --host 0.0.0.0 --port $PORT --workers 1   # OpenAPI docs at /docs
```

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness, case-store reachability, investigator readiness, queue length |
| POST | `/api/v1/alerts` | Ingest an alert; creates a case and queues its investigation. `202`; `?wait=true` blocks until done (`200`) |
| GET | `/api/v1/cases` | Case queue, in priority order. Filters `status`, `action`; paging `limit` (≤ 200), `offset` |
| GET | `/api/v1/cases/{id}` | Full case: transaction, all agent outputs, report, validation, pipeline trace, decisions, audit trail |
| GET | `/api/v1/cases/{id}/report` | Presented report with its validation and rejected reports (JSON), or `?format=markdown` |
| GET | `/api/v1/cases/{id}/audit` | Audit trail |
| POST | `/api/v1/cases/{id}/decision` | Analyst decision |

### Alert

Give exactly one of:
- `transaction`: a full `CanonicalTransaction` (source `API`);
- `transaction_id`: a transaction from the synthetic India dataset, standing
  in for the transaction-monitoring feed (source `SYNTHETIC_FEED`). Only
  `transactions_features.csv` is read; labels are never loaded.

Optional: `alert_id` (defaults to the transaction's `metadata.alert_id`) and
`source_system`.

- **Label firewall.** Ground-truth fields (`is_fraud`, `risk_label`,
  `scenario_id`) are removed before the case is stored, whatever the caller
  sends.
- **Duplicates.** A second alert for the same transaction
  (`source_dataset:raw_record_id`) returns the existing case (`200`,
  `duplicate: true`). A failed case does not block a new one.
- **Queue limit.** More than `SENTINEL_MAX_PENDING_CASES` (default 50)
  queued investigations → `429` with `Retry-After`.
- **Ingest key.** When `SENTINEL_INGEST_API_KEY` is set, ingestion requires
  the `X-API-Key` header. This protects the endpoint that triggers LLM calls
  and database writes. It is meant for a server-side alert source; a key
  embedded in the browser UI would be public.

### Case lifecycle

```
RECEIVED → INVESTIGATING → AWAITING_REVIEW → DECIDED (decisions may be revised)
                         ↘ INVESTIGATION_FAILED
```

- **One worker.** Investigations run one at a time on one in-process worker
  thread, using one `Investigator` (models and Neo4j connection created once,
  warmed up at start). This fits Render's 512 MB and the Groq free tier.
- **Restart safety.** At start-up, cases left `RECEIVED` / `INVESTIGATING`
  are queued again (`INVESTIGATION_REQUEUED` audit event).
- **Failures.** An exception during an investigation →
  `INVESTIGATION_FAILED`, with only the exception type stored.
- **What a completed case holds.** Every pipeline output: `agent1_output` …
  `validation_output`, `rejected_reports`, `pipeline_trace`,
  `pipeline_status`, `halt_reason`.
- **Halted case.** A `HALTED` case (no risk score) is `AWAITING_REVIEW`
  without a report.

### Queue summary and priority

`summary` copies values from the agents: risk score, recommended action,
score-band action, confidence, SAR recommendation, report generator,
validation status and pipeline status. Nothing is recomputed. Two fields are
derived:
- `requires_human_review` is false only when the report is `VALIDATED` and
  the pipeline `COMPLETE`.
- `priority_rank` orders the queue: BLOCK 5, ESCALATE 4, HUMAN_REVIEW 3,
  MONITOR 2, CLEAR 1, then risk score (descending), then oldest first. Cases
  not yet investigated rank 0.

### Analyst decision

Request:
- `analyst_id` (letters, digits, `. _ @ -`);
- optional `analyst_name`;
- `action`: one of BLOCK / MONITOR / ESCALATE / CLEAR, the actions in the
  project plan;
- `rationale` (required).

Allowed only once the investigation is complete (`AWAITING_REVIEW` or
`DECIDED`); otherwise `409`.

The decision stores, alongside the analyst's choice, what the analyst was
shown:
- the system's recommended action and risk score;
- the report run id and its validation status;
- `agrees_with_system`;
- `decided_at_utc`.

A new decision supersedes the previous one (`supersedes_decision_id`). All
decisions are kept, and each one adds an `ANALYST_DECISION` audit event with
the analyst id as actor. The update is conditional on the previous decision
id, so two concurrent decisions cannot both apply (`409`).

### Audit trail

Append-only events: `CASE_CREATED`, `INVESTIGATION_STARTED`,
`INVESTIGATION_COMPLETED` (pipeline status, action, score, report run id,
generator, validation status), `INVESTIGATION_FAILED`,
`INVESTIGATION_REQUEUED`, `ANALYST_DECISION`. Each has an id, a UTC time,
an actor and details.

### Case store (`SENTINEL_CASE_STORE`)

| Backend | Use | Notes |
|---|---|---|
| `json` (default) | Local development | One file per case in `SENTINEL_CASE_DIR` (default `var/cases`, gitignored); atomic writes |
| `mongodb` | Render / hosted | `MONGODB_URI`, `MONGODB_DATABASE` (default `sentinel_ai`), collection `cases`; indexes on transaction key, status and queue order |

Both backends store the same JSON document, keyed by `case_id`. Status
changes and decisions are conditional updates, and audit events and
decisions are only appended. A completed case is about 150 KB.
`tests/test_api.py` runs the same store tests against both backends, the
MongoDB ones in a temporary database that is dropped afterwards.

### Errors

| Code | Meaning |
|---|---|
| `401` | Missing or invalid ingest key |
| `404` | Unknown case, unknown feed transaction, or no report |
| `409` | Invalid state for a decision, or a concurrent change |
| `422` | Request validation (Pydantic) |
| `429` | Queue full |
| `503` | Case store unreachable, or synthetic feed not configured |

Exception messages are never returned or stored.

### CORS

`SENTINEL_CORS_ORIGINS` lists the allowed origins, comma-separated
(default: local Vite and React dev servers). `*` is refused at start-up.
Methods are GET and POST, headers `Content-Type` and `X-API-Key`, with no
credentials.

### Prototype limitations

- **Self-declared analyst identity.** The analyst id is supplied by the
  caller; there is no login. Decisions record who claimed to decide, not an
  authenticated user. A real deployment needs SSO or OIDC in front of the
  decision endpoint. Open decision for the project owner.
- **Synthetic data only.** Every case and `/health` response carries
  `prototype_notice`: synthetic or public-dataset data, mock evidence
  providers, not banking infrastructure.
- **One process.** The worker queue lives in memory, so run one instance.
  Interrupted cases are recovered at the next start.
