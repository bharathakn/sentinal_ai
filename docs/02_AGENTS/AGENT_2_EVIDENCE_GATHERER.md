# Sentinel AI — Phase 6: Agent 2 Evidence Gatherer

## Purpose

Agent 2 accepts a `CanonicalTransaction` and `Agent1Output`, queries all seven
evidence provider categories concurrently, and aggregates results into a
validated `Agent2Output`.

## Architecture

```
CanonicalTransaction + Agent1Output
    → EvidenceGathererAgent.gather()
        → asyncio.gather() [8 concurrent provider calls]
            → CORE_BANKING   : get_account_history(sender.account_id)
            → KYC            : get_kyc_data(sender.account_id)
            → DEVICE_REGISTRY: check_device(sender.account_id, device.device_id)
            → BENEFICIARY    : get_beneficiary(receiver.account_id)
            → SANCTIONS_SUBJ : screen_subject(sender.account_name)
            → SANCTIONS_ACC  : screen_account(sender.account_id)
            → GEOLOCATION    : check_geolocation(sender.account_id, lat, lon, ...)
            → NEWS           : news_provider.search(customer_name or account_id)
    → Agent2Output
```

## Implementation Status

**Phase 6 — Agent 2 Evidence Gatherer: COMPLETE**
- `EvidenceGathererAgent` with asyncio concurrency
- `Agent2Output` Pydantic schema
- `SentinelState` TypedDict (LangGraph-compatible pipeline state)
- 73 tests covering all required scenarios
- 559 total tests passing

## Files

| File | Purpose |
|------|---------|
| `src/agents/agent2/evidence_gatherer.py` | Main agent implementation |
| `src/agents/agent2/output_schema.py` | Agent2Output, Agent2Status, ProviderResult |
| `src/agents/agent2/__init__.py` | Package |
| `src/agents/sentinel_pipeline.py` | SentinelState TypedDict (pipeline state) |
| `tests/test_agent2_evidence_gatherer.py` | 73 tests |

## Concurrency

- All 8 provider calls are launched via `asyncio.gather()`.
- Sync providers run in a bounded `ThreadPoolExecutor` (max 8 workers) via `run_in_executor()`.
- Per-provider timeout: 15s (configurable). Timeout → `timed_out=True, PROVIDER_ERROR`.
- One failure never cancels other providers.

## Failure Semantics

| Scenario | Outcome |
|----------|---------|
| Provider fails | `PARTIAL`, failed provider in `failed_providers` |
| Provider times out | `timed_out=True`, `PROVIDER_ERROR` |
| Missing identifier | `VALIDATION_ERROR` for that provider only |
| All fail | `FAILED` |
| NO_ARTICLES / NOT_FOUND | Valid success result |

**Critical invariants:**
- Failed sanctions ≠ NO_MATCH (clean). Preserved as PROVIDER_ERROR.
- Timeout ≠ successful empty response.
- Missing evidence ≠ safe finding.
- Agent 1 anomaly score is never modified.
- No stack traces or API keys in output.

## LangGraph Integration

LangGraph is not yet installed. `SentinelState` TypedDict in
`src/agents/sentinel_pipeline.py` is directly compatible with LangGraph's
state annotation. When installed, wrap agents as graph nodes.

## Agent 2 does NOT do

- Risk scoring (Agent 4)
- Explanation generation (Agent 5)
- Network analysis (Agent 3)
- MongoDB persistence (future)
- Score modification or fabrication