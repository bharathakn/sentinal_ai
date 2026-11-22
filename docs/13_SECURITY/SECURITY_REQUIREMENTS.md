# FILE: docs/13_SECURITY/SECURITY_REQUIREMENTS.md

# Security Requirements

## Secrets

Credentials and API keys must not be committed to the repository.

## External APIs

API credentials must be managed through environment configuration.

## Data

The prototype should use anonymized, public, synthetic, or mocked data as defined by the project plan.

## Evidence

Evidence should remain associated with its source and timestamp.

## Audit Trail

Analyst actions must be recorded.

## Authentication (implemented Phase 13.1)

Anyone can sign up, into a private workspace that shows only their own runs
and cases. Team accounts, which see every case, are granted only with
`scripts/manage_users.py`. Every route that takes a case or run id checks the
owner (`tests/test_signup.py` tests each one). The API takes the
analyst's identity from the server-side session, never from the request
body. Details: `docs/09_BACKEND/API_DESIGN.md` → Authentication.

## AI Safety

The LLM must not be treated as an authoritative evidence source.

Generated reports must pass deterministic validation.

## Human Oversight

A failed validation must result in human review.

## Prototype Boundary

The project should clearly distinguish prototype integrations from real banking infrastructure.

## Uploaded datasets

Uploaded rows never enter the shared graph or draw on reference evidence, and
are not sent to the LLM provider unless the analyst opts in for that file.
See `docs/09_BACKEND/API_DESIGN.md`.

## Shared graph

No runtime request writes to the shared Neo4j graph. Agent 3 stages the
investigated transaction and always rolls back; only loader scripts write.
