# FILE: docs/10_FRONTEND/DASHBOARD.md

# Compliance Dashboard

## Purpose

Provide a single interface for compliance analysts to review investigated cases.

## Main Areas

### Case Queue

Display cases and prioritize them according to investigation/risk information.

### Case Detail

Display complete information for an individual investigation.

### Risk Score

Display:

- score
- risk level
- confidence
- validation status

### Evidence

Display key findings and their source information.

### Network Graph

Display relevant account relationships interactively.

### Audit Report

Display the generated investigation report.

### Action Panel

Provide analyst action controls.

The project plan identifies:

- Block
- Monitor
- Escalate
- Clear

## Audit

Analyst confirmation must be logged with analyst information and timestamp.

## Implementation (Phase 14)

IMPLEMENTED in `frontend/`: React 19 + TypeScript, built with Vite, plain
CSS with light and dark themes, and `react-force-graph-2d` for the network.
It talks only to the Phase 13 API (`docs/09_BACKEND/API_DESIGN.md`) at
relative `/api/...` URLs, so the session cookie stays first-party. Locally
the Vite dev server proxies `/api` to FastAPI; on Vercel a rewrite does.

| Area (requirement above) | Implementation |
|---|---|
| Sign-in | Username and password, "Keep me signed in" on by default. A returning analyst with a live session goes straight to the queue. When a session expires, the analyst returns to sign-in with a message. |
| Case queue | API priority order: recommended action, then risk score, then age. Tabs for awaiting review, all, decided, in progress and failed. Each row shows the risk-score bar, report validation badge, halted flag, status or decision, and age. Refreshes every 15 s. "Submit alert" takes a synthetic transaction id. |
| Case detail | Header with amount, channel, accounts, time and a synthetic-data badge. Tabs: Report, Evidence, Network, Audit trail, Pipeline. The page polls while the investigation runs. |
| Risk score | Score, recommended action, confidence, validation status and band strip; band thresholds come from the case's own Agent 4 config snapshot. Also shows overrides, SAR/STR recommendation with its "system recommendation only" note, evidence coverage, unavailable signals, policy versions, and the per-signal breakdown. Nothing is recomputed in the browser. |
| Evidence | Agent 2 provider table (source, MOCK/SYNTHETIC mode, status, entity, retrieval time) and every evidence fact by section with its source agent and source; filterable. |
| Network graph | `GET /cases/{id}/network`: accounts and transfers from the stored Agent 3 findings plus the investigated transfer, highlighted. Sender, receiver and finding accounts are coloured. Clicking a finding highlights its accounts; clicking an account lists its transfers. Tooltips are HTML-escaped. |
| Audit report | Every report statement shows its fact-id citations; clicking one shows the fact's value, source, agent, mode and observation time. Statements are labelled by origin (LLM / template / system). Also shown: Output Validator results per check, the rejected-report count, regulatory references with excerpt, page and UNVERIFIED status, and a link to the Markdown export. Unvalidated reports carry a warning. |
| Action panel | Block, Escalate, Monitor or Clear, with a required rationale. The decision is recorded against the signed-in analyst, shown with name and time, and can be revised; history is kept. The system recommendation is shown as advice: "The decision is yours". |
| Audit | Timeline of the case audit events: actor, time, key details. |

Prototype boundary: a "Prototype · synthetic data" marker in the top bar,
the API's `prototype_notice` on the queue, and a synthetic-data badge on each
case.

### Demonstration set (`scripts/seed_demo_cases.py`)

Five transactions drawn with seed 14 from the labelled India scenarios, as
specified: two fraudulent (layering network, fraud-ring hub), two legitimate
and one borderline (mixed travel). Labels are used only to choose the
transactions and to print the comparison; they never reach the agents or the
case store. The choice does not depend on the system's output.

Result, 2026-11-22: template reports, AuraDB graph.

| Transaction | Dataset label (not given to agents) | Recommended action | Risk score | Report |
|---|---|---|---|---|
| TXN_IND_202608_005924 | FRAUDULENT / layering network | ESCALATE | 60.68 | VALIDATED |
| TXN_IND_202608_003970 | FRAUDULENT / fraud-ring hub | ESCALATE | 60.32 | VALIDATED |
| TXN_IND_202608_003630 | LEGITIMATE | CLEAR | 3.29 | VALIDATED |
| TXN_IND_202608_003184 | LEGITIMATE | CLEAR | 3.61 | VALIDATED |
| TXN_IND_202608_005602 | BORDERLINE / mixed travel | CLEAR | 24.30 | VALIDATED |

The borderline case scores just below the MONITOR threshold (25). This is
shown as is: the demo is not tuned to its own outcome.

### Verification

- **Unit tests:** `npm test` (Vitest + Testing Library): API client
  (same-origin credentials, 401 handling, error messages), formatting, the
  router, HTML escaping, sign-in, citation display, and the decision flow
  (the request body never carries an identity).
- **Browser run:** headless Chrome against the real API on 2026-11-22 —
  sign-in, queue, report with an opened citation, network graph, evidence,
  recording a decision and the resulting audit trail, dark mode and 390-px
  mobile width. No page errors.
