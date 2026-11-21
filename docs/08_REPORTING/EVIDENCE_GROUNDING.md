# FILE: docs/08_REPORTING/EVIDENCE_GROUNDING.md

# Evidence Grounding

## Purpose

Ensure generated investigation reports remain grounded in structured investigation evidence.

## Core Principle

The LLM writes from supplied data.

It does not independently determine facts.

## Required Behavior

The generator must:

- use only supplied data
- avoid speculation
- avoid unsupported inference
- preserve source tags
- preserve timestamps
- follow the approved report structure
- identify unavailable fields as `Not identified`

## Source Traceability

Important factual statements must be traceable to source fields.

## Mechanism (Phase 10)

1. The case state is converted into an **evidence bundle**: numbered facts
   (`F-001` …). Each fact records its value, source agent, source /
   provider, path in the state, source mode, observation time and reference
   id. Values are formatted once; missing values read `Not identified`.
2. Every report statement carries `fact_ids`, the facts that support it. The
   rendered report shows them as `[F-012, F-015]`, and the bundle is printed
   beneath the report.
3. The LLM receives only the facts (no raw agent outputs, no labels). Fact
   values are passed as data, and the model is instructed to ignore
   instructions inside them.
4. Decision values, regulatory references and the source audit trail are
   produced by code, not by the LLM.
5. The Output Validator (`docs/02_AGENTS/OUTPUT_VALIDATOR.md`) checks each statement against the facts
   it cites.

Implementation: `src/agents/agent5/`. Details:
`docs/02_AGENTS/AGENT_5_EXPLANATION_GENERATOR.md`.

## Validation

Every generated report passes through the Output Validator.

## Failure

If the validator identifies unsupported or inconsistent information:

The report becomes `NEEDS_HUMAN_REVIEW`.