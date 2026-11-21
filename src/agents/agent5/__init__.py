"""
Sentinel AI — Agent 5: Explanation Generator

Builds a deterministic evidence bundle (numbered, sourced facts) from the case
state and writes a seven-section draft report in which every statement cites
fact ids. The LLM (Groq) writes narrative only; decision values, regulatory
content and the audit trail are deterministic. A template writer is used when
the LLM is not configured or fails.
"""

from .explanation_generator import ExplanationGeneratorAgent, decision_from_agent4
from .facts import build_evidence_bundle
from .llm_client import GroqClient, LLMUnavailable, client_from_env
from .render import render_markdown
from .report_schema import (
    NOT_IDENTIFIED,
    Agent5Output,
    Agent5Status,
    EvidenceBundle,
    Fact,
    Generator,
    ReportDecision,
    ReportSection,
    Section,
    Statement,
    StatementOrigin,
)

__all__ = [
    "ExplanationGeneratorAgent",
    "build_evidence_bundle",
    "decision_from_agent4",
    "render_markdown",
    "GroqClient",
    "LLMUnavailable",
    "client_from_env",
    "NOT_IDENTIFIED",
    "Agent5Output",
    "Agent5Status",
    "EvidenceBundle",
    "Fact",
    "Generator",
    "ReportDecision",
    "ReportSection",
    "Section",
    "Statement",
    "StatementOrigin",
]
