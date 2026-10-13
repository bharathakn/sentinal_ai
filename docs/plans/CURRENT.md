# FILE: docs/plans/CURRENT.md

# Current Project State

## Project

Sentinel AI

## Current Phase

Foundation — Data normalization layer.

## Current Objective

Canonical Transaction Schema implemented and tested. Next: Development environment & secrets configuration, then ML pipeline baseline.

## Completed

- Project concept defined
- Five-agent architecture defined
- Investigation flow defined
- Technology stack selected (Groq API, MongoDB Atlas, Neo4j, FastAPI, React, Mock Banking APIs)
- Prototype datasets identified & raw dataset directories organized (`dataset/raw/ieee_cis`, `dataset/raw/paysim`, `dataset/raw/regulatory/`, `dataset/raw/sanctions/`)
- Repository structure and documentation audit initialized
- Evidence sources identified
- Dashboard requirements identified
- Validation architecture defined
- Custom Synthetic India Dataset generated and validated (STATUS: COMPLETED & VERIFIED — SYNTHETIC DATA)
- **Canonical Transaction Schema implemented** (`src/schemas/canonical_transaction.py`)
  - Pydantic v2 `CanonicalTransaction` model with validation rules
  - IEEE-CIS adapter (`src/schemas/adapters/ieee_cis_adapter.py`)
  - PaySim adapter (`src/schemas/adapters/paysim_adapter.py`)
  - India Synthetic adapter (`src/schemas/adapters/india_adapter.py`)
  - 82 tests passing (`tests/test_canonical_schema.py`)
  - Full schema documentation (`docs/16_DATA/CANONICAL_TRANSACTION_SCHEMA.md`)

## In Progress

None.

## Next Major Milestones

1. Development environment & secrets configuration (`.env`)
2. ML pipeline baseline model development (Agent 1)
3. Neo4j graph database setup & bulk ingestion (Agent 3)
5. FastAPI ingestion
7. Agent 1
8. Agent 2
9. Agent 3
10. Agent 4
11. Agent 5
12. Output Validator
13. LangGraph integration
14. MongoDB persistence
15. Dashboard
16. Evaluation
17. End-to-end testing

## Current Blockers

None documented.

## Important Rule

Update this document whenever the active development phase changes.