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

## Known issue: cycle query limit (found 2026-11-22, not fixed)

`_CYCLES` returns an arbitrary 50 cycles. Accounts in the demo graph have up
to 91 in one window, and real SUSPICIOUS_CLUSTER findings were lost (2 of 168
sampled cases). The in-memory graph used for uploads
(`src/agents/agent3/dataset_graph.py`) examines up to 5,000. Changing the
Neo4j query changes detection results, so re-run the evaluation with it.
