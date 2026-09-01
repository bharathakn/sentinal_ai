# FILE: docs/09_BACKEND/API_DESIGN.md

# API Design

## Purpose

Define the backend API boundary for Sentinel AI.

## Primary Entry Point

FastAPI.

## Alert Ingestion

The system requires an endpoint for receiving suspicious transaction alerts.

The alert contains the transaction information needed to create a case.

## Case

The backend must expose the information required by the dashboard to display:

- case information
- investigation status
- risk score
- evidence
- network findings
- report
- validation
- recommended action

## Analyst Action

The backend must accept analyst decisions from the dashboard and preserve the associated audit information.

## API Principle

API contracts should use structured validation.

Pydantic is the project's validation technology.