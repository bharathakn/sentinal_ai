# FILE: CLAUDE.md

# Sentinel AI — Claude Code Instructions

## Project Context

Sentinel AI is an AI-assisted financial transaction investigation system.

Read the relevant documentation before making changes.

## Documentation Hierarchy

Start with:

* `docs/00_PROJECT/PROJECT_OVERVIEW.md`
* `docs/00_PROJECT/REQUIREMENTS.md`
* `docs/01_ARCHITECTURE/SYSTEM_ARCHITECTURE.md`

For agent-specific work, read the corresponding file under:

`docs/02_AGENTS/`

For machine-learning work, read:

`docs/04_MACHINE_LEARNING/`

For graph/network work, read:

`docs/05_GRAPH/`

For compliance/risk work, read:

`docs/07_RISK_AND_COMPLIANCE/`

For report generation and validation, read:

`docs/08_REPORTING/`

For frontend work, read:

`docs/10_FRONTEND/`

For testing, read:

`docs/12_TESTING/`

For security, read:

`docs/13_SECURITY/`

For current project status:

`docs/plans/CURRENT.md`

## Core Rules

* Do not invent requirements.
* Do not modify unrelated functionality.
* Inspect existing project structure before creating new files.
* Reuse existing functionality where appropriate.
* Preserve documented architectural decisions.
* Keep agent handoffs structured and validated.
* Treat source provenance as a first-class requirement.
* Do not allow generated reports to bypass the validation layer.
* Do not treat LLM output as authoritative evidence.
* Keep regulatory mappings explicit and documented.
* Keep prototype/mock integrations clearly distinguished from production integrations.
* Update relevant documentation when behavior or architecture changes.
* Add tests for new behavior.
* Do not expose secrets or credentials.

## Evidence Grounding

The explanation generator must only receive structured evidence supplied by the investigation pipeline.

Generated reports must not introduce unsupported facts.

If validation fails, the report must not be treated as validated.

## Documentation Rule

Do not create documentation merely for the sake of creating files.

Create or update documentation when it represents durable project knowledge, requirements, architecture, decisions, feature behavior, or operational knowledge.

## Current Work

Always check:

`docs/plans/CURRENT.md`

before continuing unfinished work.
