# Sentinel AI — API and Secrets Registry

## 1. Purpose

This document defines all external credentials and service configuration required by Sentinel AI.

This file must NEVER contain actual secrets.

Never write real API keys, passwords, tokens, connection strings, or private credentials into this document.

---

# 2. Credential Categories

Sentinel AI may use credentials for:

- Groq API (External LLM Provider - Free API key)
- NewsAPI (Structured public news evidence)
- MongoDB Atlas (Case object & report persistent storage)
- Neo4j / Neo4j Aura (Financial network graph database)

The prototype does not require real banking, KYC, device-registry, beneficiary, or geolocation credentials.

Those services are intentionally mocked.

---

# 3. Groq API (LLM Provider)

## Purpose

Used by Agent 5 (Explanation Generator) for structured investigation-report generation.

## Secret

`GROQ_API_KEY` (Free Tier API Key).

## Model

Configurable via environment setting (e.g. `GROQ_MODEL`). Do not hardcode model choices.

## Configuration

The application must obtain the credential through the project's secure environment configuration (`.env`).

Never hard-code the key in source code.

Never commit it to Git.

Never place it inside Markdown documentation.

---

# 3.1 Service Role Architecture Distinction

Sentinel AI clearly distinguishes the following components:

- **Groq API**: External LLM Provider for explanation & report generation.
- **Mock Banking APIs**: Core Banking, KYC, Device Registry, Beneficiary Database, Geolocation, Transaction Alert Source (Simulated internal services; no external credentials required).
- **MongoDB Atlas**: Case object & investigation output persistent storage.
- **Neo4j**: Financial account/transaction graph & network analysis.
- **NewsAPI**: Structured public-news evidence.
- **Regulatory / Sanctions Sources**: Approved offline source data (FATF, RBI, OFAC, UN).

---

# 4. NewsAPI

## Purpose

Used by the Evidence Gatherer for structured news searches in the prototype.

## Secret

NewsAPI key.

## Configuration

The application must obtain the key through the secure environment/secrets mechanism.

The NewsAPI integration must fail gracefully if the service is unavailable.

---

# 5. MongoDB Atlas

## Purpose

Stores Sentinel case objects and investigation results.

Potential stored information includes:

- Case identifier
- Original alert
- Agent outputs
- Validation result
- Final report
- Analyst action
- Audit information

## Credentials

MongoDB connection configuration must be stored securely.

Never hard-code credentials.

---

# 6. Neo4j Aura

## Purpose

Stores the transaction/account graph used by Agent 3.

## Credentials

The connection URI and authentication information must be provided through secure environment configuration.

Never hard-code passwords.

---

# 7. Mock Services

The following services are intentionally mocked:

- Core Banking
- KYC
- Device Registry
- Beneficiary Database
- Geolocation
- Transaction Monitoring Alert Source

No external credentials are required for these services.

---

# 8. Services That Must Not Be Added Without Approval

Agents must not independently introduce:

- Real banking APIs
- Real KYC providers
- Aadhaar APIs
- Real customer-information providers
- Real bank credentials
- Paid financial-data APIs
- Unapproved third-party data providers

If a real external service appears necessary, the agent must stop and request approval.

---

# 9. Secret Handling Rules

Never:

- Print secrets in logs
- Commit secrets
- Put secrets in Markdown
- Put secrets in source code
- Put secrets in screenshots
- Include secrets in error messages
- Send secrets to another AI model

Environment configuration should reference secrets without exposing their values.

---

# 10. Missing Credential Behavior

If a credential is missing:

The application should fail clearly and safely.

It should identify:

- Which service is unavailable
- Which configuration is missing
- How the developer can configure it

It must not print the secret value.

---

# 11. Prototype Principle

External services should not unnecessarily prevent local development.

Where practical:

External dependency

↓

adapter/interface

↓

mock implementation

This allows the system to be developed and tested without requiring every external service to be available.