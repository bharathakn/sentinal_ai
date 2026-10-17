# FILE: docs/06_EVIDENCE/EVIDENCE_PIPELINE.md

# Evidence Pipeline

## Purpose

Collect and normalize investigation evidence from multiple sources and supply
it to Agent 2 (Evidence Gatherer) for downstream risk analysis.

## Implementation Status

- **Phase 5 — Mock Evidence Infrastructure: COMPLETE**
  - Seven provider interfaces implemented
  - Six deterministic mock sources backed by a single synthetic fixture registry
  - NewsAPI integrated behind a provider interface (mock + live implementations)
  - 167 new tests covering all providers, cross-service consistency, and error handling

## Sources

| # | Source | Type | Status | Module |
|---|--------|------|--------|--------|
| 1 | Core Banking | Mock (synthetic) | Phase 5 complete | `src/evidence/providers/core_banking.py` |
| 2 | KYC | Mock (synthetic) | Phase 5 complete | `src/evidence/providers/kyc.py` |
| 3 | Device Registry | Mock (synthetic) | Phase 5 complete | `src/evidence/providers/device_registry.py` |
| 4 | Beneficiary | Mock (synthetic) | Phase 5 complete | `src/evidence/providers/beneficiary.py` |
| 5 | Sanctions | Mock (synthetic) | Phase 5 complete | `src/evidence/providers/sanctions.py` |
| 6 | Geolocation | Mock (synthetic) | Phase 5 complete | `src/evidence/providers/geolocation.py` |
| 7 | News (NewsAPI) | Mock or Live | Phase 5 complete | `src/evidence/providers/news/` |

No real banking, KYC, sanctions, device, or geolocation systems are integrated.
Sanctions results are entirely synthetic. No real OFAC, UN, or RBI lists are consulted.

## Synthetic Data — Single Source of Truth

All mock providers read from **`src/evidence/fixture_data.py`**.

No provider hardcodes its own account profiles. Cross-service consistency is
enforced at the fixture level.

### Synthetic Scenarios

| Identifier | Description |
|------------|-------------|
| `ACC001` | Normal sender. Registered in Bengaluru. KYC verified. Clean sanctions. |
| `ACC002` | Established beneficiary. Known to ACC001. KYC verified. Clean sanctions. |
| `ACC003` | New beneficiary account (2 days old). KYC pending. Suspicious scenario. |
| `ACC004` | High-risk account. KYC flagged. PEP. Sanctions matched (synthetic). |
| `DEV001` | Known registered device for ACC001. |
| `DEV002` | New device — not previously registered to any account. |
| `DEV003` | Shared device — associated with ACC001, ACC003, ACC004 (risk signal). |
| `SANC001` | Synthetic sanctions-matched subject: "Synthetic Fraudster One". |
| `SANC002` | Synthetic non-matched subject. |

### Cross-Service Consistency Rules

- If Core Banking says ACC001 debited to ACC002, Beneficiary must recognize ACC002.
- If KYC says ACC001 is registered in Bengaluru, Geolocation must use that location.
- If Sanctions maps ACC004 to SANC001 (match), ACC004 must not return clean in any scenario.
- Account age in Beneficiary must agree with account_opening_date in the fixture.
- avg_debit_amount_inr in Core Banking statistics must agree with actual debit transactions.

## Evidence Response Contract

All seven providers return responses extending `EvidenceResponse` (see `src/evidence/schemas.py`).

### Status Values

| Status | Meaning |
|--------|---------|
| `FOUND` | Provider responded; entity recognised; data present. |
| `NOT_FOUND` | Provider responded; entity not in records. |
| `NO_MATCH` | Screening returned no match (sanctions, news). Not same as NOT_FOUND. |
| `MATCH_FOUND` | Screening returned at least one match. |
| `NO_ARTICLES` | News search complete; zero results. Not proof of no adverse news. |
| `VALIDATION_ERROR` | Bad/missing request field. |
| `PROVIDER_ERROR` | Provider unavailable, timeout, malformed response. |
| `AUTH_ERROR` | API authentication failure or rate limit. |

### Source Mode

| `source_mode` | Meaning |
|---------------|---------|
| `MOCK` | Result from deterministic synthetic mock provider. |
| `LIVE` | Result from real external API call. |

Caller must not mix results from MOCK and LIVE providers without knowing their provenance.

## NewsAPI Integration

NewsAPI is the only real external evidence source in Phase 5.

### Provider Selection

Set `SENTINEL_NEWS_PROVIDER` environment variable:
- `mock` (default): Uses `MockNewsProvider`. No external calls. Safe for all tests.
- `live`: Uses `NewsAPIProvider`. Requires `NEWS_API_KEY` environment variable.

**There is no silent fallback.** If `live` is configured and the key is missing,
`AUTH_ERROR` is returned immediately.

### Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `NEWS_API_KEY` | For `live` mode only | NewsAPI authentication key |
| `SENTINEL_NEWS_PROVIDER` | No (default: `mock`) | Provider selection |

Set these in `.env` (not committed). See `.env.example` for the template.

### Key Security Rules

- `NEWS_API_KEY` is read only from the environment.
- It is never logged, never included in responses, never printed in error messages.
- It is excluded from Git via `.gitignore` (`.env`, `.env.*`).

### Interpretation Rules

- `NO_ARTICLES` ≠ confirmed clean. Absence of results may reflect query specificity.
- Articles mentioning similarly-named entities are preserved for human review.
- Do not treat a news article as a confirmed match without verification.

## FastAPI Application

All seven providers are exposed via a single FastAPI application.

**Start the server:**
```bash
.venv/bin/uvicorn src.evidence.app:app --reload --port 8001
```

**OpenAPI docs:** http://localhost:8001/docs

### Endpoints

| Method | Path | Provider |
|--------|------|---------|
| `GET` | `/health` | Health check |
| `GET` | `/evidence/banking/{account_id}` | Core Banking |
| `GET` | `/evidence/kyc/{account_id}` | KYC |
| `GET` | `/evidence/device/{account_id}/{device_id}` | Device Registry |
| `GET` | `/evidence/beneficiary/{account_id}` | Beneficiary |
| `POST` | `/evidence/sanctions/screen-subject` | Sanctions (by name) |
| `POST` | `/evidence/sanctions/screen-account` | Sanctions (by account ID) |
| `GET` | `/evidence/geolocation/{account_id}?lat=&lon=&city=&country=` | Geolocation |
| `POST` | `/evidence/news/search` | News |

## Evidence Lifecycle

```
Source Provider
  → Request validation
  → Fixture / API lookup
  → Normalize to EvidenceResponse
  → Attach source, source_mode, status, retrieved_at, request_id
  → Return to Agent 2 (Phase 6)
```

## Testing

| Test File | Tests | Coverage |
|-----------|-------|---------|
| `test_evidence_fixtures.py` | 20 | Fixture internal consistency |
| `test_evidence_core_banking.py` | 19 | Core banking provider |
| `test_evidence_kyc.py` | 14 | KYC provider |
| `test_evidence_device.py` | 16 | Device registry provider |
| `test_evidence_beneficiary.py` | 14 | Beneficiary provider |
| `test_evidence_sanctions.py` | 19 | Sanctions provider |
| `test_evidence_geolocation.py` | 15 | Geolocation provider |
| `test_evidence_news.py` | 25 | Mock + live news, error handling |
| `test_evidence_cross_service.py` | 25 | Cross-service consistency |

Run evidence tests only:
```bash
.venv/bin/python -m pytest tests/test_evidence_*.py -v
```

## Evidence Principles

Evidence must remain distinguishable from:
- Model predictions (`Agent1Output.anomaly_score`)
- Calculated risk scores
- LLM-generated explanations

Every response includes `source`, `source_mode`, `retrieved_at`, and `request_id`
to support provenance tracking.

## Known Limitations and Future Replacement Paths

1. **Mock banking, KYC, device, beneficiary, geolocation**: Replace with real bank API
   integrations (core banking APIs, KYC bureau APIs, device intelligence services).
2. **Mock sanctions**: Replace with real OFAC, UN, and RBI list API calls. Add fuzzy
   matching and confidence scoring for name variations.
3. **NewsAPI**: Already using the real API when configured. Future enhancement: add
   date filtering defaults and entity disambiguation.
4. **Geolocation distance**: Currently Haversine straight-line distance. Could be
   enhanced with travel-time checks using actual timestamps.
5. **Feature coverage**: Geolocation `is_anomalous` threshold (500 km) is fixed.
   A production system would use dynamic thresholds per customer profile.

## Phase 5 → Phase 6 Boundary

Phase 5 provides:
- `EvidenceResponse` Pydantic models ready for Agent 2 consumption.
- Provider functions callable from Python (no HTTP required for Agent 2).
- FastAPI endpoints for manual testing and integration.

Phase 6 (Agent 2 — Evidence Gatherer) will:
- Orchestrate all seven providers in parallel.
- Aggregate results into a structured `Agent2Output`.
- Wire the output into the LangGraph state graph.