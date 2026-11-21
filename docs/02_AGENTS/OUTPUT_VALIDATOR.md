# Output Validator

## Status

IMPLEMENTED (Phase 11). Code: `src/agents/validator/`. Validator version `1.0.0`.

## Purpose

Verify that the generated investigation report is consistent with the
structured investigation data before it is treated as validated.

## Design principle

The validator is deterministic and does not use an LLM. It checks the
report (`agent5_output`) against:
- its own evidence bundle;
- a fresh rebuild of that bundle from the case state;
- the Risk Assessor output (Agent 4).

## Checks

All checks are required. A report is `VALIDATED` only if every check passes;
otherwise it is `NEEDS_HUMAN_REVIEW`.

| Check | What it verifies |
|---|---|
| STRUCTURE | Seven sections, in order, with the expected titles, none empty. Every statement cites at least one fact, and every cited id exists. Code-added citations (`added_fact_ids`) are a subset of the citations and appear only on LLM statements. No upstream agent output is missing. |
| BUNDLE_INTEGRITY | The bundle hash recomputes, and fact ids are sequential. The bundle equals a fresh rebuild from the case state, which proves every value derives from the agents' outputs. Every fact has a source, a field path and a value. The Source Audit Trail cites every fact. |
| CITATION_GROUNDING | Every identifier, date, time and number in a statement appears in a fact that the statement cites. |
| DECISION_CONSISTENCY | The report's `decision` equals Agent 4's. The first Recommended Action statement is the code-written decision line, with the same action and score. An action name (CLEAR … BLOCK) in LLM text must appear in a cited fact. LLM SAR/STR wording must not contradict the recommendation: no "no SAR" when one is recommended, and no "SAR recommended" when it is not. |
| REGULATORY | Reference ids anywhere ⊆ Agent 4's approved matches. Every approved match is reported in the Regulatory Assessment section. Only code writes that section. LLM text names no regulator or regulation (FATF, RBI, PMLA, FIU, "Recommendation n", …). |
| LANGUAGE | LLM text contains no conclusive or accusatory wording ("confirmed fraud", "is a money mule", "proves", "laundered", "guilty", …). The check is negation-aware, so "not a confirmed identification of a money mule" passes. |
| LABEL_LEAKAGE | No dataset label (FRAUDULENT, LEGITIMATE, BORDERLINE, SCENARIO_n, MULE_SUSPECT, label field names) appears in statements or facts. The case transaction carries no ground-truth fields. |

### Grounding rules (`src/agents/agent5/grounding.py`, shared with Agent 5)

- **Tokens:**
  - *Identifiers* are letter-led codes containing a digit, such as
    `ACC_IND_000917`, `CASE-…`, `AGENT3.LAYERING.v2`, `P2P`, `INR_5L_10L`,
    plus UUIDs. They are compared exactly.
  - *Dates* (`YYYY-MM-DD`) and *times* (`HH:MM[:SS]`) are compared exactly.
  - *Numbers* are compared numerically after removing thousands separators,
    so `5000` = `5,000.00` and `14` = `14.0`. Rounded values do not match:
    `270` ≠ `270.1` and `0.2` ≠ `0.240`.
- **What counts as a fact's text:** label, value, source agent, source, mode,
  reference id, field path, and the formatted observation time. The raw ISO
  timestamp is excluded, so its digits cannot support unrelated numbers.
- **Paraphrases:** digits inside a fact's identifiers support a paraphrase,
  so `30d` supports "30-day". "Agent n" names are not numbers. `(N facts)`
  counts in the audit trail and fact references (`F-012`) are ignored.

### Known limit

The validator proves that every concrete token is supported by a cited fact.
It cannot prove that the *meaning* of a sentence is right. Example: an
"average debit" described as the average of all transactions. Fact labels
are written to be explicit, and the report is always reviewed by a human.

## Result (`ValidationOutput`)

- **Identity:** `validation_run_id`, `validator_version`, `validated_at_utc`,
  `case_id`, `transaction_id`.
- **The report checked:** `report_run_id` (the report's `agent5_run_id`),
  `report_generator`, `bundle_hash`.
- **Outcome:** `status` (VALIDATED / NEEDS_HUMAN_REVIEW), `checks` (per check:
  pass/fail, items checked, issues with section, statement index, origin,
  text and reason), `checks_passed` / `checks_total`.
- **`analyst_warning`:** set when the report is not validated.

## Pipeline stage and fallback policy (`ValidationStage`)

Runs after Agent 5, both in `Investigator` and in the future LangGraph graph.

1. Validate the presented report. Set `state["validation_output"]` and the
   report's `validation_status`.
2. If an **LLM** report fails, write a **template** report from the **same
   evidence bundle** and validate it.
   - If it passes, the template report is presented
     (`status FALLBACK_TEMPLATE`, with `fallback_reason` naming the failed
     checks). The LLM report and its validation are kept in
     `state["rejected_reports"]` for audit.
   - If it also fails, the LLM report is presented as `NEEDS_HUMAN_REVIEW`.
3. A report that fails validation is never presented as validated. Its
   warnings start with "Report NOT validated", and the case is flagged for
   human review.

Template reports quote fact values verbatim, so they are expected to
validate.

## Evaluation (2026-11-21, synthetic India cases)

| Run | Result |
|---|---|
| Template reports, 148 cases (all scenarios) | 148 VALIDATED |
| LLM reports, first prompt / validator iteration, 6 cases | 0 / 6 validated: missing identifier citations, plus validator false positives (fixed) |
| LLM reports, final, 13 cases (one per scenario + 2 normal) | 6 reached the LLM: 6 / 6 VALIDATED and presented. 7 hit the Groq free-tier token limit and used validated template reports |
| Total presented | 13 / 13 VALIDATED |

Genuine LLM defects caught during development:
- a rounded duration (270 for 270.1);
- an action or identifier named without the fact that states it;
- "no SAR is automatically filed" in a case where a SAR is recommended;
- a "30 days" claim cited against facts that never mention 30 days.

## Agent 5 measures that support validation

- **Entity labels:** evidence facts name their entity, e.g. "Device
  registration status (ACC_IND_000917 / DEV_IND_001046)".
- **Identifier citation completion:** when an LLM statement names an
  identifier that appears in exactly-sourced evidence but does not cite that
  fact, Agent 5 adds the citation and records it in `added_fact_ids`. Action
  names are completed only with the decision fact stating *that* action.
  Numbers, dates and times are never completed.
- **Prompt rule:** every token in a statement must come from a fact cited by
  that statement.

## Running

```bash
PYTHONPATH=. .venv/bin/python scripts/run_investigation.py TXN_IND_202608_000977   # prints validation table
PYTHONPATH=. .venv/bin/python scripts/evaluate_pipeline.py --reports template      # validation at scale
PYTHONPATH=. .venv/bin/python scripts/evaluate_pipeline.py --per-scenario 1 --normal 2 --reports llm
```

Tests: `tests/test_output_validator.py`. Each check has a deliberately broken
report that must fail, and its near-miss, which must pass.
