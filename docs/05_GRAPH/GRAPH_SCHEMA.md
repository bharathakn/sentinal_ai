# FILE: docs/05_GRAPH/GRAPH_SCHEMA.md

# Neo4j Graph Schema — Phase 7

## Purpose

Represent financial accounts and directed money-transfer relationships for
network investigation by Agent 3 (Network Analyser).

## Nodes

### `:Account`

Represents a bank/payment account.

| Property        | Type   | Required | Description                                      |
|-----------------|--------|----------|--------------------------------------------------|
| `account_id`    | string | Yes      | Stable account identifier (unique constraint)    |
| `source_dataset`| string | Yes      | Originating dataset (e.g. `INDIA_SYNTHETIC`)     |
| `account_name`  | string | No       | Account holder name (PaySim only; absent elsewhere) |

## Relationships

### `-[:TRANSFERRED_TO]->`

Represents a single directed money transfer from sender to receiver.
Multiple transfers between the same two accounts are stored as separate
relationship instances, each with a unique `tx_graph_id`.

| Property          | Type   | Required | Description                                       |
|-------------------|--------|----------|---------------------------------------------------|
| `tx_graph_id`     | string | Yes      | Idempotency key: `<raw_record_id>::<source_dataset>` |
| `raw_record_id`   | string | Yes      | Original record identifier from source dataset    |
| `source_dataset`  | string | Yes      | Originating dataset                               |
| `amount`          | float  | Yes      | Transaction amount (stored as Neo4j float)        |
| `amount_str`      | string | Yes      | Amount as decimal string (preserves precision)   |
| `currency`        | string | Yes      | ISO-4217 currency code (e.g. `INR`, `USD`)        |
| `timestamp_utc`   | string | No       | UTC ISO-8601 timestamp string                     |
| `channel`         | string | Yes      | Payment channel (`UPI`, `NEFT`, `RTGS`, etc.)     |
| `status`          | string | Yes      | Transaction status (`SUCCESS`, `FAILED`, etc.)    |

## Constraints and Indexes

| Name                      | Type        | Target                        | Rationale                              |
|---------------------------|-------------|-------------------------------|----------------------------------------|
| `account_id_unique`       | Uniqueness  | `Account.account_id`          | Prevents duplicate Account nodes       |
| `account_source_dataset`  | Index       | `Account.source_dataset`      | Supports dataset-scoped account queries|

Both use `IF NOT EXISTS` — schema init is idempotent (safe on every startup).

## Idempotency Strategy

Each `TRANSFERRED_TO` relationship is MERGEd on `tx_graph_id`. This key is:

```
tx_graph_id = f"{raw_record_id}::{source_dataset}"
```

The key is deterministic and stable. Re-ingesting the same record updates
existing relationship properties rather than creating a duplicate.

Multiple distinct transactions between the same two accounts produce separate
relationship instances, each with a different `tx_graph_id`.

## Network Analysis (Future — Agent 3)

The graph structure supports investigation of:

- Multi-hop transfer paths (`A → B → C → …`)
- Incoming transfer concentration (fan-in)
- Outgoing rapid forwarding (fan-out / layering)
- Shared account membership
- Fraud-ring detection

Pattern detection queries belong to the Agent 3 implementation and are NOT
part of this Phase 7 infrastructure.

## Provenance

Network findings from Agent 3 must retain:

- Graph query source (e.g., path query on TRANSFERRED_TO)
- Timestamp of the graph query execution
- `tx_graph_id` values referenced by the finding

## Data Loading Scope (Phase 7)

Initial load: India Synthetic dataset, ≤ 500 rows.

**Not loaded in Phase 7:**
- Full PaySim dataset (6.3M rows — deferred)
- IEEE-CIS dataset (for ML pipeline only, not graph)
- Live banking transactions