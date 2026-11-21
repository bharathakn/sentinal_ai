"""
Sentinel AI — Agent 4: Risk Assessor

Deterministic, configuration-driven risk scoring over Agent 1–3 outputs,
with score breakdown, recommended action, confidence, SAR/STR
recommendation and regulatory matches from the approved mapping registry.

No LLM is used. Weights and mappings are PROPOSED pending approval
(see config.py and regulatory_mapping.py).
"""

from .config import Agent4Config, RecommendedAction, RiskSignal
from .output_schema import Agent4Output, Agent4Status, ConfidenceLevel
from .risk_assessor import RiskAssessorAgent

__all__ = [
    "RiskAssessorAgent",
    "Agent4Config",
    "Agent4Output",
    "Agent4Status",
    "ConfidenceLevel",
    "RecommendedAction",
    "RiskSignal",
]
