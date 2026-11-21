# FILE: docs/14_OPERATIONS/DEVELOPMENT_SETUP.md

# Development Setup

## Required Environment

The project requires:

- Python 3.11+
- Virtual environment (`.venv`)
- Git (work is committed directly on `main`)
- Docker (local Neo4j for Agent 3)
- Optional: MongoDB Atlas (case storage)
- Optional: Groq API key (free tier, for report generation agents)

## Local Python Environment Setup

```bash
# 1. Clone repository and navigate to root
cd Sentinal_AI

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install core dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### Dependencies Installed (`requirements.txt`)

- **Core ML**: `xgboost>=2.0.0`, `scikit-learn>=1.4.0`, `shap>=0.45.0`
- **Data & Schemas**: `pandas>=2.1.0`, `numpy>=1.26.0`, `pydantic>=2.0.0`
- **Persistence**: `joblib>=1.3.0`
- **Testing**: `pytest>=8.0.0`, `pytest-cov>=5.0.0`

## Dataset Directory Layout

Raw datasets are read-only and placed under `dataset/raw/`:

```
dataset/
├── raw/
│   ├── ieee_cis/               # train_transaction.csv, train_identity.csv, test_*.csv
│   ├── paysim/                 # PS_20174392719_1491204439457_log.csv
│   ├── regulatory/fatf/        # fatf-recommendations-2026.pdf
│   ├── regulatory/rbi/         # RBI Master Directions on Fraud Risk Management.pdf
│   ├── sanctions/ofac/         # ofac_sdn.csv
│   └── sanctions/un/           # un_consolidated_sanctions.xml
└── processed/
    └── custom_india/           # custom_india_transactions.csv (synthetic data)
```

## Local Neo4j (Docker)

```bash
docker run -d --name sentinel-neo4j --restart unless-stopped \
  -p 127.0.0.1:7474:7474 -p 127.0.0.1:7687:7687 \
  -v sentinel_neo4j_data:/data \
  -e NEO4J_AUTH="neo4j/<choose-a-password>" neo4j:5-community
```

Set in `.env`: `NEO4J_URI=bolt://localhost:7687`, `NEO4J_USERNAME=neo4j`,
`NEO4J_PASSWORD=<password>`, `NEO4J_DATABASE=neo4j`.

AuraDB works the same way (`NEO4J_URI=neo4j+s://…`). **`.env` decides which
database the scripts and the live tests use.** Live integration tests create
and delete their own prefixed test accounts there. The graph must be loaded
(step 3 below) into whichever database `.env` points to. Otherwise Agent 3
reports PARTIAL ("graph appears empty or not loaded"). The loader writes in
bulk (500 per transaction), so a full load into AuraDB takes seconds.

## Rebuild the India investigation world

Steps 1–2 in one idempotent command (also the Render build step; see
`DEPLOYMENT.md`): `PYTHONPATH=. .venv/bin/python scripts/build_artifacts.py [--force]`.

```bash
# 1. Generate the India synthetic dataset v2 (validated; ~2 s)
PYTHONPATH=. .venv/bin/python scripts/generate_synthetic_dataset.py
# 2. Train the India behavioural model for Agent 1 (~5 s)
PYTHONPATH=. .venv/bin/python scripts/train_india_model.py
# 3. Load all transactions into Neo4j (labels are never loaded; seconds)
PYTHONPATH=. .venv/bin/python scripts/load_india_sample_graph.py --reset-india
```

## Run investigations

```bash
# One transaction through Agents 1–5 and print the draft report
# (--template: no LLM call; --no-report: stop after Agent 4; --report-out FILE.md)
PYTHONPATH=. .venv/bin/python scripts/run_investigation.py TXN_IND_202608_000977
# End-to-end evaluation on a labelled sample (~30 s locally)
PYTHONPATH=. .venv/bin/python scripts/evaluate_pipeline.py
# ... plus report generation + Output Validator pass rate
PYTHONPATH=. .venv/bin/python scripts/evaluate_pipeline.py --reports template
PYTHONPATH=. .venv/bin/python scripts/evaluate_pipeline.py --per-scenario 1 --normal 2 --reports llm
```

These scripts use `SENTINEL_EVIDENCE_BACKEND=india_synthetic` by default.
Unit tests use the `fixture` backend. The report uses Groq when `GROQ_API_KEY`
is set. On the free tier (~8,000 tokens/min), generate at most about one
report per 40 s; otherwise the template writer is used.

Browser UI: http://localhost:7474

## Run the API (Phase 13)

```bash
.venv/bin/uvicorn src.api.main:app --port 8000 --workers 1     # OpenAPI docs: http://localhost:8000/docs
curl -X POST 'localhost:8000/api/v1/alerts?wait=true' -H 'Content-Type: application/json' \
     -d '{"transaction_id": "TXN_IND_202608_000977"}'
curl localhost:8000/api/v1/cases
```

The API loads `.env` and defaults to the India synthetic evidence backend.
Cases go to `var/cases/` (`SENTINEL_CASE_STORE=json`), or to MongoDB Atlas
with `SENTINEL_CASE_STORE=mongodb`. Endpoints and lifecycle:
`docs/09_BACKEND/API_DESIGN.md`.

## Running Verification Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

About 1,050 tests. `tests/conftest.py` loads only the `NEO4J_*` keys from `.env`;
the 29 live Neo4j integration tests skip when those are not set. The case-store
tests in `tests/test_api.py` also run against MongoDB when `MONGODB_URI` is
set (only `MONGODB_*` keys are read), in a temporary database that is dropped. The suite
forces the template report writer (no LLM calls). Set
`SENTINEL_LIVE_LLM_TESTS=1` to run the single live Groq test. The Agent 4
regulatory-excerpt provenance test needs `pdftotext` (poppler-utils) and
skips without it.

## Machine Learning Execution Workflows

### 1. Model Inference (No Training)

Trained artifacts are cached in `models/xgboost/v1/` and `models/isolation_forest/v1/`. For inference, load existing artifacts directly:

```python
from src.ml.agent1_scorer import Agent1Scorer
from src.schemas.adapters.ieee_cis_adapter import IEEECISAdapter

scorer = Agent1Scorer()
tx = IEEECISAdapter.from_row(raw_row)
score_result = scorer.score(tx)
# score_result["xgboost"]["fraud_probability"]
# score_result["iforest"]["anomaly_score"]
```

### 2. Threshold Calibration

Re-run threshold sweeps on the held-out validation split:

```bash
python scripts/run_threshold_calibration.py
```

### 3. Training Models

#### Development Mode (15% Stratified Sample)
Recommended for development on standard developer laptops (requires 4–8GB RAM):

```bash
SENTINEL_SAMPLE_FRAC=0.15 python scripts/train_pipeline.py
SENTINEL_SAMPLE_FRAC=0.15 python scripts/train_isolation_forest.py
```

#### Full IEEE-CIS Mode (590,540 rows)
Full dataset training is fully supported by the software without row limits or column truncation:

```bash
SENTINEL_SAMPLE_FRAC=full python scripts/train_pipeline.py
SENTINEL_SAMPLE_FRAC=full python scripts/train_isolation_forest.py
```

> [!NOTE]
> **Hardware Policy**: Full-dataset training merges 590,540 transactions and 144,233 identity rows into a 434-column DataFrame. Fitting 500 gradient-boosted trees and 200 isolation trees requires $\ge 16\text{GB}$ available host RAM. Machines with less available RAM should use the validated 15% sample baseline to prevent Linux OOM-killer termination.

## Service Roles & Architecture Distinction

- **Groq API**: External LLM Provider (used for structured explanation and investigation report generation)
- **Mock Banking APIs**: Core Banking, KYC, Device Registry, Beneficiary Database, Geolocation (simulated internal services)
- **MongoDB Atlas**: Case object & investigation output persistent storage
- **Neo4j**: Financial account/transaction graph & network analysis
- **NewsAPI**: External structured public-news evidence
- **Regulatory / Sanctions Sources**: Approved offline source data (FATF, RBI, OFAC, UN)