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

## AI Safety

The LLM must not be treated as an authoritative evidence source.

Generated reports must pass deterministic validation.

## Human Oversight

A failed validation must result in human review.

## Prototype Boundary

The project should clearly distinguish prototype integrations from real banking infrastructure.