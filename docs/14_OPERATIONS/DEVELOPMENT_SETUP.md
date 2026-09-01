# FILE: docs/14_OPERATIONS/DEVELOPMENT_SETUP.md

# Development Setup

## Required Environment

The project plan specifies:

- Python 3.11
- backend environment
- frontend environment
- Neo4j
- MongoDB Atlas
- optional Redis
- required model/API credentials

## Development Components

Backend:

Python/FastAPI.

Frontend:

React.

ML:

XGBoost, Scikit-learn, Pandas, NumPy, SHAP.

Graph:

Neo4j.

Orchestration:

LangGraph.

Storage:

MongoDB Atlas.

LLM:

Claude API.

## Environment Configuration

All environment-specific configuration must be kept outside committed source code.

A documented example environment configuration should be maintained.

## Verification

After setup, verify each major dependency independently before beginning full pipeline integration.