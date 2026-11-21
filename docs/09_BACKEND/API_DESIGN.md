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
| GET | `/health` | Liveness, case-store reachability, investigator readiness, queue length (public) |
| POST | `/api/v1/auth/login` | Sign in: `username`, `password`, `remember` (default true); sets the session cookie |
| POST | `/api/v1/auth/logout` | Sign out (session deleted server-side) |
| GET | `/api/v1/auth/me` | Signed-in analyst |
| POST | `/api/v1/auth/password` | Change own password (`current_password`, `new_password`) |
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
- **Who may ingest.** A signed-in analyst, or a server-side alert source
  sending `X-API-Key` equal to `SENTINEL_INGEST_API_KEY`. The key grants
  ingestion only, not case access. When the variable is unset, any
  `X-API-Key` is refused. The `CASE_CREATED` audit event names the
  submitter: the username, or `ingest-api-key`.

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

Request: `action` (BLOCK / MONITOR / ESCALATE / CLEAR, the actions in the
project plan) and `rationale` (required). The analyst is the signed-in user:
the decision records their username and display name. A body that tries to
supply an identity is rejected (`422`).

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
| `401` | Not signed in, session expired, account disabled, wrong credentials, or invalid ingest key |
| `404` | Unknown case, unknown feed transaction, or no report |
| `409` | Invalid state for a decision, or a concurrent change |
| `422` | Request validation (Pydantic) |
| `429` | Queue full, or sign-in locked after repeated failures (`Retry-After`) |
| `503` | Case store unreachable, or synthetic feed not configured |

Exception messages are never returned or stored.

### CORS

`SENTINEL_CORS_ORIGINS` lists the allowed origins, comma-separated
(default: local Vite and React dev servers). `*` is refused at start-up.
Methods are GET and POST, headers `Content-Type` and `X-API-Key`, with no
credentials.

### Authentication (Phase 13.1, `src/api/auth.py`)

Goal: real sign-in that analysts rarely have to repeat.

| Aspect | Behaviour |
|---|---|
| Accounts | Created by an administrator with `scripts/manage_users.py` (`create`, `reset-password`, `disable`, `enable`, `list`); no public sign-up. Usernames are lower-case and case-insensitive at sign-in. |
| Passwords | scrypt (n=2^14, r=8, p=1, random salt); at least 10 characters. Never accepted on the command line. |
| Session | Random 256-bit token in an `HttpOnly`, `SameSite=Lax`, `Secure` cookie (`sentinel_session`). The store keeps only its SHA-256. |
| How long | "Keep me signed in" (default): expires after 7 days without use (`SENTINEL_SESSION_IDLE_DAYS`) and at most 30 days after sign-in (`SENTINEL_SESSION_MAX_DAYS`). Without it: 12 hours, and the cookie ends with the browser session. |
| Sign-out / revocation | Sign-out deletes the session. Disabling a user, a password reset, or a password change signs the user out of all other devices. |
| Brute force | 5 failed sign-ins for a username within 15 minutes lock it for the rest of the window (`429`). Unknown usernames and wrong passwords get the same error and similar timing. |
| Storage | Same backend as cases: `var/auth.json` (json, file mode 600), or the MongoDB collections `users` and `sessions` (a TTL index removes expired sessions). |

**The browser must see the API as first-party.** Browsers increasingly block
third-party cookies, so the Vercel UI must call the API through a Vercel
rewrite (`/api/*` → Render) rather than calling the Render domain directly.
`SameSite=Lax` also stops other sites from making state-changing requests
with the cookie.

### Prototype limitations

- **No roles and no SSO.** Every account is an analyst. Accounts are
  managed with the script.
- **Lockout is per process.** The failure counter lives in memory, so a
  restart clears it.
- **Synthetic data only.** Every case and `/health` response carries
  `prototype_notice`: synthetic or public-dataset data, mock evidence
  providers, not banking infrastructure.
- **One process.** The worker queue lives in memory, so run one instance.
  Interrupted cases are recovered at the next start.
