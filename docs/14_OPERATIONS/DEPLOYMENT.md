# Deployment

Target hosting chosen by the project owner (2026-11-21): **Vercel** for the
frontend, **Render** for the Python backend. Deployment happens after Phase 14;
this document records the target design so that earlier phases stay
compatible with it.

## Target topology

```
Browser ──► Vercel (React analyst UI, static build)          Phase 14
              │  HTTPS, API base URL from a Vercel env var
              ▼
            Render Web Service (FastAPI + agents, Python)     Phase 13
              ├─► Neo4j AuraDB Free      (graph, neo4j+s://)
              ├─► Groq API               (Agent 5 LLM; server-side key only)
              ├─► NewsAPI                (optional; mock by default)
              └─► MongoDB Atlas M0       (case store, SENTINEL_CASE_STORE=mongodb)
```

The agents, ML models and LLM calls run only on Render. Vercel serves static
files and holds no secrets.

## Environment-driven configuration

Nothing in the code is tied to the local machine. Local development and
production differ only in environment variables:

| Variable | Local | Render |
|---|---|---|
| `NEO4J_URI` | `bolt://localhost:7687` | `neo4j+s://<id>.databases.neo4j.io` |
| `NEO4J_USERNAME` / `NEO4J_PASSWORD` | Docker credentials | AuraDB credentials |
| `NEO4J_DATABASE` | `neo4j` | `neo4j` |
| `SENTINEL_EVIDENCE_BACKEND` | `fixture` (tests) | `india_synthetic` |
| `SENTINEL_REQUIRE_IEEE_MODELS` | `true` | `false` |
| `SENTINEL_NEWS_PROVIDER` | `mock` | `mock` (or `live` + `NEWS_API_KEY`) |
| `GROQ_API_KEY` | `.env` | Render secret |
| `GROQ_MODEL` | default `openai/gpt-oss-120b` | same |
| `SENTINEL_REPORT_GENERATOR` | `llm` | `llm` (template fallback is automatic) |
| `SENTINEL_CASE_STORE` | `json` | `mongodb` |
| `MONGODB_URI` | `.env` | Render secret |
| `MONGODB_DATABASE` | default `sentinel_ai` | same |
| `SENTINEL_CORS_ORIGINS` | default localhost dev servers | the Vercel origin, e.g. `https://<app>.vercel.app` |
| `SENTINEL_INGEST_API_KEY` | empty (open) | a random secret if alerts come from a server-side source |
| `LANGSMITH_TRACING` | `false` | `false` |
| `SENTINEL_COOKIE_SECURE` | `true` (`false` only for plain-http clients other than localhost browsers) | `true` |
| `SENTINEL_SESSION_IDLE_DAYS` / `SENTINEL_SESSION_MAX_DAYS` | `7` / `30` | same |

The Neo4j driver accepts `bolt://`, `neo4j://` and `neo4j+s://` URIs, so
switching to AuraDB needs no code change. Credentials are never committed;
they are entered in the Render dashboard.

## Artifacts on Render

`dataset/` and `models/` are gitignored. The India artifacts are rebuilt during
the Render build instead of being committed. The generator and trainer are
seeded, and rebuilding produces byte-identical CSVs and model files (verified
2026-11-21; about 5 s).

```
Build command:  pip install -r requirements.txt && python scripts/build_artifacts.py
Start command:  uvicorn src.api.main:app --host 0.0.0.0 --port $PORT --workers 1
Health check:   /health
```

The IEEE-CIS models need the 1.8 GB raw Kaggle dataset and are not deployed.
`SENTINEL_REQUIRE_IEEE_MODELS=false` lets Agent 1 start without them; India
transactions use the India-native model. If an IEEE-CIS transaction were
submitted, Agent 1 would return a structured `FAILED` output rather than
crashing.

## Sign-in on the hosted deployment

- **Vercel project.** Root directory `frontend`, framework Vite, output
  `dist`. `frontend/vercel.json` holds the rewrites; replace
  `RENDER-SERVICE-NAME` with the Render service host before deploying. No
  Vercel environment variables are needed.
- **Proxy the API through Vercel.** The Vercel app proxies the API with a
  rewrite in `vercel.json`, so the session cookie is first-party:

  ```json
  { "rewrites": [ { "source": "/api/:path*", "destination": "https://<render-service>.onrender.com/api/:path*" } ] }
  ```

  The UI calls relative `/api/...` URLs. Do not call the Render domain from
  the browser: third-party cookies are blocked by many browsers.
- **Avoid long requests through the proxy.** Vercel proxied requests have a
  time limit, so the UI should not use `POST /api/v1/alerts?wait=true`.
  Submit the alert, then poll the case.
- **Load the demo cases** the same way:
  `SENTINEL_CASE_STORE=mongodb python scripts/seed_demo_cases.py`.
- **Create accounts from a developer machine** against Atlas:

  ```bash
  SENTINEL_CASE_STORE=mongodb MONGODB_URI=... python scripts/manage_users.py create <username> --name "<Full Name>"
  ```

## Graph on AuraDB

The graph is loaded once from a developer machine. Render does not load it.

```
NEO4J_URI=neo4j+s://... NEO4J_USERNAME=... NEO4J_PASSWORD=... \
  python scripts/load_india_sample_graph.py --reset-india
```

The current graph has 1,500 accounts and 10,000 transfers. The loader writes
500 transfers per transaction (`load_batch_unwind`); loading the full graph
into AuraDB took 8 s on 2026-11-21, against an estimated hour with
one transaction per record. The pipeline is slower against a remote graph:
about 0.9 s per investigation, against 0.07 s locally. AuraDB Free
allows 200,000 nodes and 400,000 relationships. AuraDB Free pauses idle
instances and deletes them if they are not resumed. The original AuraDB
instance in `.env` no longer resolves, most likely for this reason. Before a
demo, check that the instance is running.

## Constraints that later phases must respect

1. **Memory.** The API server peaks at about 445 MB RSS after
   investigations (measured 2026-11-22 against AuraDB and Atlas). Of that,
   about 240 MB is libraries, 115 MB the Agent 1 models and 25 MB the India
   store. Render's free and Starter instances have 512 MB, which leaves
   about 65 MB. Models load once per process, and the API runs one worker.
   Do not load full-size DataFrames per request. If Render reports
   out-of-memory restarts, move to the next instance size.
2. **Ephemeral filesystem.** Render's disk is wiped on every deploy and
   restart, so the JSON case store would lose all cases. **Decided
   (Phase 13):** MongoDB Atlas, `SENTINEL_CASE_STORE=mongodb`. Atlas Network
   Access must allow Render's outbound addresses; on the free tier these are
   not fixed, so use `0.0.0.0/0` with a strong database password. Cases
   interrupted by a restart are queued again at start-up.
3. **Cold starts.** Render's free services sleep when idle, and the first
   request takes about a minute. The UI should show a loading state.
4. **CORS.** The FastAPI app must allow the Vercel origin. Use an env var,
   not a wildcard.
5. **Secrets.** The Groq key lives on Render only. Vercel variables exposed
   to the browser (e.g. `VITE_*`) must contain only the API base URL.
6. **LLM availability.** Agent 5 falls back to the template writer when Groq
   fails, so a missing or rate-limited key never blocks an investigation.
   The free Groq tier allows about 8,000 tokens/min, roughly one LLM report
   per 40 s. A demo with several analysts needs Groq's paid Dev tier or
   should accept template reports.
7. **Python version.** `.python-version` pins the version that Render uses.
8. **Synthetic data only.** The deployed system serves synthetic data and
   mock providers. Pages must not present results as real customer data.
