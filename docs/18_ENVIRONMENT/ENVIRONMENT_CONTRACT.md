# Sentinel AI — Environment Contract

## 1. Purpose

This document defines how Sentinel AI receives configuration from its environment.

Application code must not depend on credentials being hard-coded.

---

# 2. Configuration Categories

The project may require configuration for:

- Application environment
- Groq API (LLM Provider)
- NewsAPI
- MongoDB
- Neo4j
- Mock services
- Logging
- Model paths
- Dataset paths

---

# 3. Secret Configuration

Secrets must be provided through secure environment configuration.

Potential secret categories include:

- `GROQ_API_KEY` (Groq API credential)
- `NEWS_API_KEY` (NewsAPI credential)
- MongoDB authentication (`MONGODB_URI`)
- Neo4j authentication (`NEO4J_URI`, `NEO4J_PASSWORD`)

Actual values must never be stored in this document or committed to Git.

---

# 4. Dataset Configuration

Dataset locations should be configurable.

The application must not depend on a user's personal absolute filesystem path.

For example, the system should not permanently depend on:

`/mnt/data/...`

or another developer-specific directory.

Paths must be resolved through project-relative configuration or environment configuration.

---

# 5. Database Configuration

MongoDB and Neo4j connection settings must be configurable without changing application source code.

Changing from one development database to another should require configuration changes rather than source-code modifications.

---

# 6. Development Environment

The development environment must support:

- Local mock services
- Local model execution
- Database connections
- External API connections
- Automated tests

The project should remain usable when optional external services are unavailable.

---

# 7. Production Separation

Development configuration and future production configuration must remain separate.

Do not assume that:

- Development credentials are production credentials
- Development databases are production databases
- Mock APIs are production APIs
- Debug logging is appropriate for production

---

# 8. Missing Configuration

When required configuration is missing:

The application should provide a clear error.

The error must identify the missing configuration name but must not expose secret values.

---

# 9. Configuration Validation

At application startup, configuration should be validated.

Invalid configuration should produce an actionable error rather than causing an unrelated runtime failure later.

---

# 10. AI Agent Rule

Agents must not:

- Invent credentials
- Invent API keys
- Hard-code passwords
- Commit secrets
- Modify secret values
- Print secrets
- Replace missing external credentials with fake credentials

If a required secret is unavailable, the agent should explain the requirement and use a mock/test path when appropriate.