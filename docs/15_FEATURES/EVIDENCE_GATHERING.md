# FILE: docs/15_FEATURES/EVIDENCE_GATHERING.md

# Feature — Evidence Gathering

## Purpose

Collect contextual evidence from defined investigation sources.

## Sources

Refer to:

`docs/02_AGENTS/AGENT_2_EVIDENCE_GATHERER.md`

## Requirements

- execute required source requests
- support concurrent source collection
- normalize results
- preserve source metadata
- preserve timestamps
- handle unavailable sources
- return structured evidence

## Prototype

Bank-specific sources are mocked.

## Output

A structured evidence object associated with the investigation case.