# FILE: docs/11_STORAGE/STORAGE_ARCHITECTURE.md

# Storage Architecture

## MongoDB

Primary case-object storage.

A case should contain the investigation information required by the project.

The project plan identifies:

- original alert
- agent outputs
- validated report
- analyst decision
- audit trail

## Neo4j

Used specifically for account and transaction relationship analysis.

## Redis

Optional prototype component.

Purpose:

Cache intermediate agent outputs and support retry/recomputation behavior.

## Separation

MongoDB:

Case persistence.

Neo4j:

Network relationships.

Redis:

Temporary/intermediate caching where used.

## Prototype Constraint

Storage choices should remain aligned with the project plan and avoid unnecessary infrastructure.