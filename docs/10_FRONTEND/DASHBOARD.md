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

## Implementation (Phase 14, redesigned in Phase 15)

`frontend/`: React 19 + TypeScript + Vite. One light theme (warm paper, serif
headlines, deep teal) at the project owner's request; fonts are bundled.

Flow: choose a file or the demo dataset → watch the five agents → final
report → resolve each finding.

| Screen | Behaviour |
|---|---|
| Landing | Upload (CSV / JSON), demo dataset, how many flagged transactions to investigate, recent runs |
| Live run | Screening counter and histogram, then one animated scene per agent: Detect, Gather, Trace, Assess, Explain + validator. Speed, skip, replay; earlier cases and stages are clickable |
| Final report | Totals, what drove each finding, a plain-words conclusion, inline analyst decision, Save as PDF |
| Cases / case | Priority queue; full report with citations, evidence, network, audit trail, pipeline |

Rules for the live view:
- It is a pure function of the run's event log (`src/lib/run.ts`). Only the
  pacing is added; each scene shows the agent's actual duration.
- A template report is never described as a validation failure unless a
  draft was rejected (`fallbackNote`).
- "Not connected" is never shown as "No record".

### Demo-run caveats (measured 2026-11-22, answer key used for evaluation only)

- 2,017 of 10,000 are flagged: 1,261 fraudulent, 330 borderline, 426 legitimate.
- These numbers are optimistic: about 70% of the demo rows are the rows the
  India model was trained on.
- The top 10 by anomaly signal are all layering cases, so the default top-5
  demo shows five similar cases, all ESCALATE at about 62.

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
