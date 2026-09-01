# FILE: docs/05_GRAPH/GRAPH_SCHEMA.md

# Neo4j Graph Schema

## Purpose

Represent financial accounts and transaction relationships for network investigation.

## Nodes

### Account

Represents a bank account in the prototype graph.

## Relationships

### TRANSFERRED_TO

Represents a transaction from one account to another.

## Relationship Information

The project plan identifies:

- amount
- timestamp
- frequency

## Network Analysis

The graph should support investigation of:

- multi-hop relationships
- incoming transaction concentration
- outgoing forwarding
- rapid fund movement
- shared account relationships
- fraud-ring patterns

## Provenance

Network findings must retain the graph-query source and timestamp associated with the result.