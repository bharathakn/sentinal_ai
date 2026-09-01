---
trigger: always_on
---

# FILE: .agents/rules/agents.md

# Agent Development Rules

Sentinel AI contains specialized investigation stages.

## Rules

* Keep each agent's responsibility clearly defined.
* Do not move responsibilities between agents without an architectural decision.
* Use structured handoffs.
* Validate agent outputs.
* Preserve source and timestamp metadata.
* Do not allow the LLM to become the authoritative source of investigative evidence.
* Keep deterministic processing separate from narrative generation.
