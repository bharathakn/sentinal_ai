# FILE: docs/01_ARCHITECTURE/SYSTEM_ARCHITECTURE.md

# System Architecture

## High-Level Flow

Bank transaction monitoring system
→ FastAPI ingestion
→ LangGraph controller
→ Agent 1
→ Agent 2
→ Agent 3
→ Agent 4
→ Agent 5
→ Output Validator
→ Compliance Dashboard
→ Analyst Review

## Major Layers

### Ingestion Layer

Responsible for receiving transaction alerts and creating investigation cases.

Technology:

FastAPI

### Orchestration Layer

Responsible for controlling investigation execution and structured handoffs.

Technology:

LangGraph

### Investigation Layer

Contains the five specialized investigation agents.

### Data Layer

Contains:

- MongoDB case storage
- Neo4j relationship graph
- ML datasets
- evidence sources

### Validation Layer

Deterministic validation of generated reports.

### Presentation Layer

React-based compliance dashboard.

## Architectural Principle

The LLM is responsible for converting structured investigation information into human-readable explanation.

It is not the authoritative source of investigative facts.

## Reliability Boundary

The Output Validator sits between report generation and analyst presentation.

A report that fails validation must be flagged for human review.