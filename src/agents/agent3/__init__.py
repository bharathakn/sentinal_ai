"""
Sentinel AI — Agent 3: Network Analyser

Analyses account-transfer relationships in Neo4j and detects suspicious
network patterns for downstream risk assessment (Agent 4).

Supported patterns
------------------
- Layering            : Multi-hop fund movement through intermediaries
- Structuring         : Repeated transfers meeting prototype heuristic criteria
- Fan-in              : Multiple sources converging on one recipient
- Fan-out             : One sender distributing to multiple recipients
- Mule-like behavior  : Receive-then-rapidly-forward with multiple parties
- Rapid forwarding    : Outgoing transfers shortly after incoming funds
- Suspicious clusters : Dense or cyclically-connected account groups

Public API
----------
- NetworkAnalyserAgent  : Main agent class
- Agent3Output          : Validated output schema
- Agent3Config          : Tunable detection thresholds
"""

from .network_analyser import NetworkAnalyserAgent
from .output_schema import Agent3Output, Agent3Status
from .config import Agent3Config

__all__ = [
    "NetworkAnalyserAgent",
    "Agent3Output",
    "Agent3Status",
    "Agent3Config",
]
