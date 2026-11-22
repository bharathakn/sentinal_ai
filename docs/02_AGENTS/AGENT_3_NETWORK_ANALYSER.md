# FILE: docs/02_AGENTS/AGENT_3_NETWORK_ANALYSER.md

# Agent 3 — Network Analyser

## Purpose

Analyze the transaction as part of a larger account network.

## Technology

Neo4j.

## Graph Model

Account:

Node.

Transaction:

Directed relationship.

Relationship properties include:

- amount
- timestamp
- frequency

## Investigation Patterns

### Layering

Rapid movement through multiple accounts.

### Structuring

Multiple transfers designed to remain below relevant thresholds.

### Shell Company Pattern

Recently created accounts receiving and forwarding significant funds with limited apparent legitimate activity.

### Fraud Ring

Multiple victim accounts connected to an intermediary or downstream account.

## Investigation Scope

The project plan includes multi-hop graph traversal.

## Output

The agent should provide structured network findings including:

- network risk level
- detected pattern
- connected-account information
- transaction aggregation
- forwarding behavior
- relevant graph query timestamp

## Provenance

Network findings must identify the graph query/source and timestamp.

## Nothing is persisted (fixed 2026-11-22)

Agent 3 used to MERGE the subject transaction, which overwrote a matching
transfer. Because `POST /api/v1/alerts` accepts a caller-supplied transaction,
that allowed tampering with the reference graph. The subject is now staged in
a transaction that is always rolled back: detectors still see it, nothing
persists. `graph_ingestion_performed` means "staged". Only the loader scripts
write to the graph. Tests: `tests/test_agent3_readonly.py` and the live
`TestSubjectNeverPersistsLive`, which fails on the old code.

## Cycle search (fixed 2026-11-22)

`_CYCLES` returned an arbitrary 50 cycles and lost real rings (the demo graph
has up to 170 candidates in one window). The bound is now 5,000; reaching it
gives PARTIAL with a warning. Re-evaluation on the same 575 cases: one more
fraudulent case shows SUSPICIOUS_CLUSTER, legitimate cases are unchanged, and
no risk score or action changed.
