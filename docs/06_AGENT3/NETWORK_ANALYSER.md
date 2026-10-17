# Sentinel AI — Agent 3: Network Analyser

## Overview

Agent 3 analyses account-transfer relationships stored in the Neo4j graph
(Phase 7) and produces structured, evidence-backed network-pattern findings
for downstream Agent 4 (Risk Assessor).

**Pipeline position:**
Agent 1 → Agent 2 → **Agent 3** → Agent 4 (future) → Agent 5 (future)

**LangGraph node:** `NetworkAnalyserAgent(state)` returns updated `SentinelState`
with `agent3_output` set.

---

## Supported Network Patterns

| Pattern | Rule ID | Detection Condition |
|---------|---------|-------------------|
| Layering | `AGENT3.LAYERING.v1` | Directed path of ≥ `min_layering_hops` hops through intermediaries |
| Structuring | `AGENT3.STRUCTURING.v1` | ≥ `structuring_min_transfers` outgoing transfers within `structuring_window_hours` |
| Fan-in | `AGENT3.FAN_IN.v1` | ≥ `fan_in_min_sources` distinct source accounts to one recipient |
| Fan-out | `AGENT3.FAN_OUT.v1` | ≥ `fan_out_min_destinations` distinct recipient accounts from one sender |
| Mule-like | `AGENT3.MULE_LIKE.v1` | ≥ `mule_min_incoming_sources` sources AND ≥ `mule_min_outgoing_destinations` destinations |
| Rapid Forwarding | `AGENT3.RAPID_FORWARDING.v1` | Outgoing within `rapid_forwarding_window_minutes` of incoming |
| Suspicious Cluster | `AGENT3.SUSPICIOUS_CLUSTER.v1` | ≥ `cluster_min_accounts` accounts AND ≥ `cluster_min_edges` edges in bounded neighbourhood |

**IMPORTANT:** All findings are ENGINEERING HEURISTIC INDICATORS. They are:
- NOT calibrated fraud probabilities
- NOT legal or regulatory determinations
- NOT final fraud risk scores (that is Agent 4's role)

---

## Detection Configuration (`Agent3Config`)

All thresholds are documented engineering heuristics with conservative defaults.

| Parameter | Default | Env var | Description |
|-----------|---------|---------|-------------|
| `max_layering_hops` | 4 | `SENTINEL_A3_MAX_LAYERING_HOPS` | Max graph depth for layering paths |
| `min_layering_hops` | 2 | `SENTINEL_A3_MIN_LAYERING_HOPS` | Minimum hops to flag as layering |
| `layering_max_elapsed_hours` | 72.0 | `SENTINEL_A3_LAYERING_MAX_ELAPSED_HOURS` | Hours window for rapid-layering context |
| `fan_in_min_sources` | 3 | `SENTINEL_A3_FAN_IN_MIN_SOURCES` | Min distinct incoming sources |
| `fan_out_min_destinations` | 3 | `SENTINEL_A3_FAN_OUT_MIN_DESTINATIONS` | Min distinct outgoing destinations |
| `structuring_min_transfers` | 3 | `SENTINEL_A3_STRUCTURING_MIN_TRANSFERS` | Min transfers in window |
| `structuring_window_hours` | 24.0 | `SENTINEL_A3_STRUCTURING_WINDOW_HOURS` | Time window for structuring check |
| `rapid_forwarding_window_minutes` | 120.0 | `SENTINEL_A3_RAPID_FWD_WINDOW_MINUTES` | Max minutes for rapid forwarding |
| `mule_min_incoming_sources` | 2 | `SENTINEL_A3_MULE_MIN_INCOMING` | Min incoming sources for mule check |
| `mule_min_outgoing_destinations` | 2 | `SENTINEL_A3_MULE_MIN_OUTGOING` | Min outgoing destinations for mule check |
| `cluster_min_accounts` | 4 | `SENTINEL_A3_CLUSTER_MIN_ACCOUNTS` | Min accounts in suspicious cluster |
| `cluster_min_edges` | 4 | `SENTINEL_A3_CLUSTER_MIN_EDGES` | Min edges in suspicious cluster |
| `transfer_query_limit` | 200 | `SENTINEL_A3_TRANSFER_QUERY_LIMIT` | Max rows per transfer query |
| `layering_path_limit` | 5 | `SENTINEL_A3_LAYERING_PATH_LIMIT` | Max layering paths returned |

---

## Required Graph Properties

Agent 3 reads from `(:Account)` nodes and `[:TRANSFERRED_TO]` relationships
established by Phase 7.

**Relationship properties used:**

| Property | Required | Purpose |
|----------|----------|---------|
| `tx_graph_id` | Yes | Idempotency key and finding reference |
| `raw_record_id` | No | Link back to source transaction |
| `amount` | No | Transfer value for pattern evidence |
| `timestamp_utc` | No | UTC ISO-8601; used for time-based checks |
| `currency` | No | Reported in findings |
| `channel` | No | Reported in findings |

Missing `timestamp_utc` values are handled explicitly — detectors exclude
pairs that cannot establish temporal ordering and report this in warnings.

---

## Output Contract (`Agent3Output`)

```python
Agent3Output(
    agent3_run_id: str,              # Unique run identifier
    transaction_id: str | None,      # Links to input CanonicalTransaction
    source_dataset: str | None,
    sender_account_id: str | None,
    receiver_account_id: str | None,
    analysed_at_utc: datetime,
    status: Agent3Status,            # COMPLETE | PARTIAL | UNAVAILABLE | FAILED | VALIDATION_ERROR
    warnings: list[str],             # Non-fatal issues
    errors: list[str],               # Empty unless FAILED
    detectors_run: list[str],
    detectors_skipped: list[str],
    sender_in_graph: bool | None,
    receiver_in_graph: bool | None,
    graph_ingestion_performed: bool,
    findings: list[NetworkFinding],
    finding_count: int,
    agent1_output_ref: str | None,
    agent2_output_ref: str | None,
    analysis_note: str,              # Documented limitations disclaimer
)
```

### Status semantics

| Status | Meaning |
|--------|---------|
| `COMPLETE` | All detectors ran; empty `findings` means no patterns met configured thresholds |
| `PARTIAL` | Some detectors ran; others failed — check `detectors_skipped` |
| `UNAVAILABLE` | No graph data (accounts not found, unconfigured DB) |
| `FAILED` | Critical failure — graph unreachable or invalid inputs |
| `VALIDATION_ERROR` | Missing sender/receiver account_id |

> **Empty `findings` with non-COMPLETE status must NOT be treated as a confirmed clean result.**

---

## Query and Traversal Limits

| Query | Bound | Reason |
|-------|-------|--------|
| Outgoing/incoming transfers | `transfer_query_limit` rows | Prevent unbounded memory |
| Layering paths | `min_layering_hops`..`max_layering_hops` hops, `layering_path_limit` paths | Bounded depth |
| Cluster neighbourhood | 2 hops, `transfer_query_limit` rows | Avoid full-graph scan |

Neo4j 5 / GQL 1.0 does not allow parameterised hop counts inside variable-length
relationship patterns. Agent 3 follows Phase 7's documented safeguard:
validated integer literals from `Agent3Config` are interpolated into the Cypher
string — never user-supplied text.

---

## Running Tests

```bash
# Unit tests only (no Neo4j required)
.venv/bin/python -m pytest tests/test_agent3_network_analyser.py -v

# Live Neo4j integration tests (requires .env)
.venv/bin/python -m pytest tests/test_agent3_integration.py -v

# Full suite
.venv/bin/python -m pytest --tb=short -q
```

### Test counts (Phase 8)

| Suite | Tests | Status |
|-------|-------|--------|
| Agent 3 unit (mocked) | 81 | ✅ all pass |
| Agent 3 live Neo4j integration | 9 | ✅ all pass (against real AuraDB) |
| Full suite (Phases 1–8) | **739** | ✅ **739 passed, 0 failed** |

---

## Pipeline Integration

```python
from src.agents.agent3 import NetworkAnalyserAgent

agent = NetworkAnalyserAgent()         # uses Agent3Config.from_env()

# Direct call (for testing)
output = agent.analyse(transaction)

# LangGraph-compatible state call
new_state = agent({"transaction": tx, "agent1_output": a1, "agent2_output": a2})
output = new_state["agent3_output"]
```

`agent3_output` is typed in `SentinelState` as `Optional[Agent3Output]`.

---

## Known Limitations and Deferred Work

1. **Agent 3 analyses the sender account only.** The receiver-centric view
   (fan-in to receiver) requires the caller to construct a separate analysis
   using the receiver as subject, or a future multi-account orchestration.

2. **Suspicious cluster is bounded to 2-hop neighbourhood.** Larger fraud rings
   spanning more hops are not detected in Phase 8. Community-detection
   algorithms (e.g., Louvain) are deferred.

3. **Structuring threshold is a prototype heuristic**, not a calibrated or
   legally authoritative figure. It must be reviewed by compliance stakeholders
   before production use.

4. **No inter-finding deduplication across detectors.** MULE_LIKE and FAN_IN/
   FAN_OUT findings from the same account are separate entries. Agent 4 should
   consolidate overlapping signals.

5. **Full Agent 3 fraud-ring analysis** (complete graph traversal, community
   detection, long-range path analysis) is deferred to the Agent 3 extension phase.

6. **Agent 4 (Risk Assessor) is not yet implemented.** Agent 3 findings are
   stored in `SentinelState["agent3_output"]` and available for Agent 4 consumption.
