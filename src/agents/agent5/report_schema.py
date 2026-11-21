"""
Sentinel AI — Agent 5: report and evidence-bundle schemas.

Grounding contract
------------------
* Every factual statement in a report cites one or more fact ids
  (``F-001`` …) from the case's :class:`EvidenceBundle`.
* The bundle is built deterministically from agent outputs; it is the only
  information the LLM receives.
* Decision values (risk score, action, SAR recommendation, regulatory
  references) are copied from Agent 4 into :class:`ReportDecision`; they are
  never produced by the LLM.
* A report is a DRAFT until the Output Validator (Phase 11) validates it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

NOT_IDENTIFIED = "Not identified"


class ReportSection(str, Enum):
    CASE_SUMMARY = "CASE_SUMMARY"
    ANOMALY_FINDINGS = "ANOMALY_FINDINGS"
    EVIDENCE_SUMMARY = "EVIDENCE_SUMMARY"
    NETWORK_ANALYSIS = "NETWORK_ANALYSIS"
    REGULATORY_ASSESSMENT = "REGULATORY_ASSESSMENT"
    RECOMMENDED_ACTION = "RECOMMENDED_ACTION"
    SOURCE_AUDIT_TRAIL = "SOURCE_AUDIT_TRAIL"


SECTION_TITLES: dict[ReportSection, str] = {
    ReportSection.CASE_SUMMARY: "1. Case Summary",
    ReportSection.ANOMALY_FINDINGS: "2. Anomaly Findings",
    ReportSection.EVIDENCE_SUMMARY: "3. Evidence Summary",
    ReportSection.NETWORK_ANALYSIS: "4. Network Analysis",
    ReportSection.REGULATORY_ASSESSMENT: "5. Regulatory Assessment",
    ReportSection.RECOMMENDED_ACTION: "6. Recommended Action",
    ReportSection.SOURCE_AUDIT_TRAIL: "7. Source Audit Trail",
}

#: Sections whose narrative the LLM may write. Regulatory Assessment and
#: Source Audit Trail are always generated deterministically.
LLM_SECTIONS: tuple[ReportSection, ...] = (
    ReportSection.CASE_SUMMARY,
    ReportSection.ANOMALY_FINDINGS,
    ReportSection.EVIDENCE_SUMMARY,
    ReportSection.NETWORK_ANALYSIS,
    ReportSection.RECOMMENDED_ACTION,
)


class SourceAgent(str, Enum):
    CASE = "CASE"
    TRANSACTION = "TRANSACTION"
    AGENT_1 = "AGENT_1"
    AGENT_2 = "AGENT_2"
    AGENT_3 = "AGENT_3"
    AGENT_4 = "AGENT_4"


class Fact(BaseModel):
    """One atomic, sourced piece of case evidence."""

    model_config = ConfigDict(frozen=True)

    fact_id: str = Field(description="Stable id within the bundle, e.g. F-001.")
    section: ReportSection = Field(description="Section the fact naturally belongs to.")
    label: str = Field(description="Human-readable name of the fact.")
    value: str = Field(description="Display value, formatted deterministically. 'Not identified' when missing.")
    source_agent: SourceAgent
    source: str = Field(description="Provider / model / component that produced the value.")
    source_field: str = Field(description="Path of the value in the case state.")
    source_mode: Optional[str] = Field(default=None, description="MOCK / LIVE / SYNTHETIC where known.")
    observed_at: Optional[str] = Field(default=None, description="UTC ISO-8601 time the source produced the value.")
    reference_id: Optional[str] = Field(default=None, description="request_id / finding_id / run id.")


class EvidenceBundle(BaseModel):
    """All facts available to the report writer for one case."""

    model_config = ConfigDict(frozen=True)

    case_id: Optional[str]
    transaction_id: Optional[str]
    built_at_utc: datetime
    facts: list[Fact]
    bundle_hash: str = Field(description="SHA-256 of the canonical JSON of `facts`.")
    builder_version: str
    missing_inputs: list[str] = Field(default_factory=list, description="Agent outputs absent from the state.")

    def get(self, fact_id: str) -> Optional[Fact]:
        for f in self.facts:
            if f.fact_id == fact_id:
                return f
        return None

    def ids(self) -> set[str]:
        return {f.fact_id for f in self.facts}


class StatementOrigin(str, Enum):
    LLM = "LLM"
    TEMPLATE = "TEMPLATE"
    SYSTEM = "SYSTEM"  # deterministic decision / regulatory / audit content


class Statement(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    fact_ids: list[str] = Field(min_length=1)
    origin: StatementOrigin
    added_fact_ids: list[str] = Field(
        default_factory=list,
        description="Citations added by code (identifier citation completion), a subset of fact_ids.",
    )


class Section(BaseModel):
    model_config = ConfigDict(frozen=True)

    section: ReportSection
    title: str
    statements: list[Statement]


class ReportDecision(BaseModel):
    """Decision values copied verbatim from Agent 4 (never from the LLM)."""

    model_config = ConfigDict(frozen=True)

    recommended_action: Optional[str] = None
    risk_score: Optional[float] = None
    score_band_action: Optional[str] = None
    confidence: Optional[str] = None
    sar_recommended: Optional[bool] = None
    sar_basis: list[str] = Field(default_factory=list)
    overrides: list[str] = Field(default_factory=list)
    regulatory_reference_ids: list[str] = Field(default_factory=list)
    config_version: Optional[str] = None
    mapping_version: Optional[str] = None


class Agent5Status(str, Enum):
    COMPLETE = "COMPLETE"                    # LLM narrative, structurally valid
    TEMPLATE = "TEMPLATE"                    # template writer by configuration / no LLM configured
    FALLBACK_TEMPLATE = "FALLBACK_TEMPLATE"  # LLM attempted and failed; template used
    PARTIAL = "PARTIAL"                      # report produced but an upstream agent output was missing
    FAILED = "FAILED"                        # no report could be produced


class Generator(str, Enum):
    LLM = "LLM"
    TEMPLATE = "TEMPLATE"


class Agent5Output(BaseModel):
    """Draft investigation report. Not validated until Phase 11 says so."""

    model_config = ConfigDict(frozen=True)

    agent5_run_id: str = Field(default_factory=lambda: str(uuid4()))
    case_id: Optional[str] = None
    transaction_id: Optional[str] = None
    generated_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: Agent5Status
    generator: Optional[Generator] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_attempts: int = 0
    fallback_reason: Optional[str] = Field(default=None, description="Sanitised reason the LLM output was not used.")
    prompt_version: Optional[str] = None
    template_version: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    sections: list[Section] = Field(default_factory=list)
    decision: ReportDecision = Field(default_factory=ReportDecision)
    evidence_bundle: Optional[EvidenceBundle] = None

    validation_status: str = Field(
        default="NOT_VALIDATED",
        description="Set only by the Output Validator. NOT_VALIDATED until then.",
    )
    report_note: str = (
        "DRAFT generated from structured, SYNTHETIC investigation evidence. Every "
        "statement cites evidence fact ids. Decision values are copied from the "
        "deterministic Risk Assessor. The report is not validated until the Output "
        "Validator has checked it, and any SAR/STR decision belongs to a qualified human."
    )

    def section(self, s: ReportSection) -> Optional[Section]:
        for sec in self.sections:
            if sec.section == s:
                return sec
        return None
