# FILE: AGENTS.md

# Sentinel AI — Agent Instructions

## Mission

Build Sentinel AI according to the documented project requirements and architecture.

## Source of Truth

The Git repository and its maintained documentation are the project source of truth.

When documentation conflicts with assumptions from a previous conversation, inspect the current repository and documented decisions.

## Before Starting Work

1. Read `CLAUDE.md`.
2. Read the relevant project documentation.
3. Inspect the existing implementation.
4. Identify affected components.
5. Check current project status.
6. Check relevant architectural decisions.
7. Produce a plan for meaningful changes.

## Implementation Boundaries

* Work only within the requested feature or task.
* Do not refactor unrelated areas without justification.
* Do not replace existing architecture without an explicit reason.
* Do not introduce dependencies without considering the existing stack.
* Do not create duplicate functionality.
* Do not silently change documented behavior.

## AI Agent Pipeline

Sentinel AI contains five specialized investigation agents:

1. Anomaly Detector
2. Evidence Gatherer
3. Network Analyser
4. Risk Assessor
5. Explanation Generator

The Output Validator is a deterministic validation layer and is not an LLM reasoning agent.

Agent handoffs must remain structured.

## Evidence

Every externally sourced investigative finding must retain source information and timestamp information where required by the project specification.

## Completion Requirements

A feature is not complete until:

* implementation is complete
* relevant tests are completed
* relevant validation is completed
* documentation is updated where necessary
* no unrelated functionality has been broken
