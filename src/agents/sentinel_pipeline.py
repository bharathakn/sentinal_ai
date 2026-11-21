"""
Sentinel AI — Investigation Pipeline State.

Defines the shared state that flows through the agent pipeline.
Implemented as a TypedDict for direct LangGraph compatibility —
when LangGraph is installed, use this as the State annotation.

Architecture
------------
Agent 1 (Anomaly Detector)  →  writes agent1_output
Agent 2 (Evidence Gatherer) →  reads agent1_output, writes agent2_output
Agent 3 (Network Analyser)  →  reads agent2_output, writes agent3_output
Agent 4 (Risk Assessor)     →  reads agent1/2/3 outputs, writes agent4_output
Agent 5 (Explanation Gen.)  →  reads agent4_output, writes final_report (future)

Rules
-----
* Each agent reads from the established state fields and writes only its own
  output field. No agent modifies another agent's output.
* The `transaction` field is immutable once set by the graph entry point.
* Optional agent outputs are None until the corresponding agent has run.
* LangGraph integration: replace `dict` with `StateGraph(SentinelState)` once
  langgraph is installed. The field names and types are designed for direct
  compatibility with LangGraph's state annotation conventions.
"""

from __future__ import annotations

from typing import Optional
from typing_extensions import TypedDict

from ..schemas.canonical_transaction import CanonicalTransaction
from .agent1.output_schema import Agent1Output
from .agent2.output_schema import Agent2Output
from .agent3.output_schema import Agent3Output
from .agent4.output_schema import Agent4Output


class SentinelState(TypedDict, total=False):
    """Shared investigation state flowing through the Sentinel AI pipeline.

    Fields
    ------
    transaction   : The canonical transaction being investigated. Required.
    agent1_output : Output from Agent 1 (Anomaly Detector). Set after Agent 1.
    agent2_output : Output from Agent 2 (Evidence Gatherer). Set after Agent 2.
    agent3_output : Output from Agent 3 (Network Analyser). Set after Agent 3.
    agent4_output : Output from Agent 4 (Risk Assessor). Set after Agent 4.

    Agent 5 field is reserved for a future phase.
    """

    transaction: CanonicalTransaction
    agent1_output: Optional[Agent1Output]
    agent2_output: Optional[Agent2Output]
    agent3_output: Optional[Agent3Output]
    agent4_output: Optional[Agent4Output]
    # agent5_output: Optional[Agent5Output]   # Phase 10: Explanation Generator
