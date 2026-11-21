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

## Supported Network Patterns (rule version v2, Phase 9.5)

v1 rules were timeless and structural ("≥3 recipients ever", "any 2-hop path").
On the full 10,000-transaction graph they flagged **100% of transactions,
including every legitimate one**. v2 anchors every rule on the investigated
transaction's timestamp T and analyses BOTH the sender and the receiver.

Analysis window: transfers in `[T − lookback_hours, T + horizon_hours]`
(default 168 h back, 24 h forward — the horizon models an investigation
performed shortly after the alert, when onward movement is visible).

| Pattern | Rule ID | v2 detection condition |
|---------|---------|------------------------|
| Layering | `AGENT3.LAYERING.v2` | Time-ordered chain **through the investigated transfer** (backward into the sender + forward from the receiver), ≥ `min_layering_hops` hops, each hop within `layering_hop_max_gap_hours` of the previous and ≥ `layering_min_amount_retention` × its amount, total ≤ `layering_max_elapsed_hours`; no repeated accounts; sub-chains suppressed |
| Structuring | `AGENT3.STRUCTURING.v2` | ≥ `structuring_min_transfers` outgoing transfers within `structuring_window_hours`, each just below a multiple of `structuring_round_unit` (within `structuring_proximity_pct`) |
| Fan-in | `AGENT3.FAN_IN.v2` | ≥ `fan_in_min_sources` distinct sources within any `fan_window_hours` window |
| Fan-out | `AGENT3.FAN_OUT.v2` | ≥ `fan_out_min_destinations` distinct recipients within any `fan_window_hours` window |
| Mule-like | `AGENT3.MULE_LIKE.v2` | Within `mule_window_hours` of an incoming transfer: ≥ `mule_min_incoming_sources` sources in, ≥ `mule_min_outgoing_destinations` destinations out **after** the money arrived, and out ≥ `mule_min_passthrough_ratio` × in |
| Rapid Forwarding | `AGENT3.RAPID_FORWARDING.v2` | Outgoing within `rapid_forwarding_window_minutes` after an incoming transfer and ≥ `rapid_forwarding_min_ratio` of its amount; all pairs for an account in one finding |
| Suspicious Cluster | `AGENT3.SUSPICIOUS_CLUSTER.v2` | Closed cycle through the account of `cluster_min_edges`..`cluster_max_cycle_length` transfers (≥ `cluster_min_accounts` accounts) where **some rotation** is strictly time-ordered (funds went round once), within `cluster_window_hours`; each account set reported once |

Missing timestamps fail temporal rules (no ordering is invented).

**IMPORTANT:** All findings are ENGINEERING HEURISTIC INDICATORS. They are:
- NOT calibrated fraud probabilities
- NOT legal or regulatory determinations (the structuring round unit is not a reporting threshold)
- NOT final fraud risk scores (that is Agent 4's role)

### Measured behaviour (v2, India dataset v2, 15–40 cases per scenario)

| Scenario | Cases with ≥1 finding | Characteristic finding |
|---|---|---|
| Layering | 100% | LAYERING 15/15 |
| Structuring | 100% | STRUCTURING 15/15 |
| Mule pass-through | 100% | MULE_LIKE, RAPID_FORWARDING |
| Fraud ring | 100% | SUSPICIOUS_CLUSTER |
| Rapid burst | 100% | FAN_OUT |
| Normal (legitimate) | ~32% | all involve an account that takes part in a fraud pattern (e.g. paying a mule) |

---

## Detection Configuration (`Agent3Config`)

All thresholds are documented engineering heuristics. Env overrides use the
`SENTINEL_A3_` prefix (see `config.py`).

| Parameter | Default | Description |
|-----------|---------|-------------|
| `lookback_hours` / `horizon_hours` | 168 / 24 | Analysis window around T |
| `max_layering_hops` / `min_layering_hops` | 5 / 3 | Layering chain length bounds |
| `layering_hop_max_gap_hours` | 6 | Max gap between consecutive hops |
| `layering_min_amount_retention` | 0.80 | Min fraction of previous hop's amount |
| `layering_max_elapsed_hours` | 72 | Max chain duration |
| `fan_in_min_sources` / `fan_out_min_destinations` | 3 / 3 | Distinct counterparties |
| `fan_window_hours` | 24 | Fan counting window |
| `structuring_min_transfers` / `structuring_window_hours` | 3 / 24 | Repetition |
| `structuring_round_unit` / `structuring_proximity_pct` | 50,000 / 0.10 | "Just below a round amount" |
| `rapid_forwarding_window_minutes` / `rapid_forwarding_min_ratio` | 120 / 0.5 | Forwarding speed and size |
| `mule_min_incoming_sources` / `mule_min_outgoing_destinations` | 2 / 1 | Mule counts |
| `mule_window_hours` / `mule_min_passthrough_ratio` | 48 / 0.70 | Pass-through |
| `cluster_min_accounts` / `cluster_min_edges` / `cluster_max_cycle_length` | 3 / 3 / 6 | Cycle size |
| `cluster_window_hours` | 72 | Cycle duration |
| `transfer_query_limit` / `layering_path_limit` | 200 / 5 | Query bounds |

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
| `PARTIAL` | Some detectors ran; others failed — check `detectors_skipped`. Also used when the graph holds fewer than `min_graph_transfers` (default 100, `SENTINEL_A3_MIN_GRAPH_TRANSFERS`) transfers in total: the graph is empty or not loaded, so "no patterns" is not a clean result |
| `UNAVAILABLE` | No graph data (accounts not found, unconfigured DB) |
| `FAILED` | Critical failure — graph unreachable or invalid inputs |
| `VALIDATION_ERROR` | Missing sender/receiver account_id |

> **Empty `findings` with non-COMPLETE status must NOT be treated as a confirmed clean result.**

---

## Query and Traversal Limits

| Query | Bound | Reason |
|-------|-------|--------|
| Outgoing/incoming transfers (sender and receiver) | analysis window, `transfer_query_limit` rows | Prevent unbounded memory |
| Layering chains | backward and forward ≤ `max_layering_hops − 1` hops each, 25 rows each, time/amount predicates evaluated in Cypher | Bounded, time-pruned expansion |
| Cycles | `cluster_min_edges`..`cluster_max_cycle_length` hops within the window, 50 rows | Bounded, window-pruned expansion |

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

1. **Counterparty contamination is reported, not suppressed.** A legitimate
   payment to an account that takes part in a fraud pattern produces findings
   about that counterparty (subject_account_id identifies which account).
   This is intended network context; Agent 4 weighs it.
2. **Cycles only.** Clusters are detected as time-ordered cycles of up to 6
   transfers. Community detection (e.g. Louvain) is deferred.
3. **Structuring round unit is a prototype heuristic**, not a calibrated or
   legally authoritative figure.
4. **No inter-finding deduplication across detectors** other than identical
   cycles. Agent 4 uses the maximum heuristic score.
5. **Horizon looks 24 h past the transaction**, modelling an investigation
   performed after the alert. For strict real-time scoring set
   `horizon_hours=0`.
