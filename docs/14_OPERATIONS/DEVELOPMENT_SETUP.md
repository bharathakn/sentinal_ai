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

Groq API (Free Tier key, model configurable).

## Service Roles & Architecture Distinction

- **Groq API**: External LLM Provider (used for structured explanation and investigation report generation)
- **Mock Banking APIs**: Core Banking, KYC, Device Registry, Beneficiary Database, Geolocation, Transaction Alert Source (Simulated internal services)
- **MongoDB Atlas**: Case object & investigation output persistent storage
- **Neo4j**: Financial account/transaction graph & network analysis
- **NewsAPI**: External structured public-news evidence
- **Regulatory / Sanctions Sources**: Approved offline source data (FATF, RBI, OFAC, UN)

## Environment Configuration

All environment-specific configuration must be kept outside committed source code.

A documented example environment configuration should be maintained.

## Verification

After setup, verify each major dependency independently before beginning full pipeline integration.