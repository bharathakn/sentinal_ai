"""
Sentinel AI — Agent 5: Explanation Generator.

Produces a seven-section DRAFT investigation report from the case state.

Pipeline
--------
1. ``build_evidence_bundle(state)`` → numbered, sourced facts (deterministic).
2. Narrative sections (Case Summary, Anomaly Findings, Evidence Summary,
   Network Analysis, Recommended Action narrative):
     * LLM (Groq) when configured: JSON statements citing fact ids,
       structurally checked; one corrective retry on malformed output.
     * otherwise, or on any LLM failure: deterministic template writer.
3. Deterministic SYSTEM content: Recommended Action decision block,
   Regulatory Assessment, Source Audit Trail.
4. Decision values copied verbatim from Agent 4 into ``decision``.

The LLM never decides the score, action, SAR recommendation or regulatory
references, and the pipeline never blocks on the LLM. The report remains
``NOT_VALIDATED`` until the Output Validator runs.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Union

from .facts import build_evidence_bundle
from .grounding import complete_identifier_citations
from .llm_client import LLMClient, LLMGenerationError, LLMUnavailable, client_from_env
from .prompt import PROMPT_VERSION, RESPONSE_SCHEMA, LLMOutputError, build_messages, parse_llm_output
from .report_schema import (
    LLM_SECTIONS,
    SECTION_TITLES,
    Agent5Output,
    Agent5Status,
    EvidenceBundle,
    Generator,
    ReportDecision,
    ReportSection,
    Section,
    Statement,
)
from .writers import TEMPLATE_VERSION, system_audit, system_decision, system_regulatory, template_narrative

logger = logging.getLogger(__name__)

_AUTO = "auto"


def _enum(v: Any) -> Optional[str]:
    return None if v is None else getattr(v, "value", str(v))


def decision_from_agent4(a4: Any) -> ReportDecision:
    if a4 is None:
        return ReportDecision()
    return ReportDecision(
        recommended_action=_enum(a4.recommended_action),
        risk_score=a4.risk_score,
        score_band_action=_enum(a4.score_band_action),
        confidence=_enum(a4.confidence),
        sar_recommended=a4.sar_recommendation.recommended,
        sar_basis=list(a4.sar_recommendation.basis),
        overrides=[o.rule_id for o in a4.overrides_applied],
        regulatory_reference_ids=sorted({m.reference_id for m in a4.regulatory_matches}),
        config_version=a4.config_version,
        mapping_version=a4.mapping_version,
    )


def assemble_sections(bundle: EvidenceBundle,
                      narrative: dict[ReportSection, list[Statement]]) -> list[Section]:
    body: dict[ReportSection, list[Statement]] = {
        ReportSection.CASE_SUMMARY: narrative.get(ReportSection.CASE_SUMMARY, []),
        ReportSection.ANOMALY_FINDINGS: narrative.get(ReportSection.ANOMALY_FINDINGS, []),
        ReportSection.EVIDENCE_SUMMARY: narrative.get(ReportSection.EVIDENCE_SUMMARY, []),
        ReportSection.NETWORK_ANALYSIS: narrative.get(ReportSection.NETWORK_ANALYSIS, []),
        ReportSection.REGULATORY_ASSESSMENT: system_regulatory(bundle),
        ReportSection.RECOMMENDED_ACTION: system_decision(bundle)
        + narrative.get(ReportSection.RECOMMENDED_ACTION, []),
        ReportSection.SOURCE_AUDIT_TRAIL: system_audit(bundle),
    }
    return [Section(section=s, title=SECTION_TITLES[s], statements=body[s]) for s in ReportSection]


UPLOAD_REPORT_NOTE = (
    "DRAFT generated from structured investigation evidence about an analyst-uploaded dataset of "
    "unverified origin. Every statement cites evidence fact ids. Decision values are copied from the "
    "deterministic Risk Assessor, whose models and policy were calibrated on synthetic data. The report "
    "is not validated until the Output Validator has checked it, and any SAR/STR decision belongs to a "
    "qualified human."
)


def _complete_citations(narrative: dict[ReportSection, list[Statement]],
                        bundle: EvidenceBundle) -> tuple[dict[ReportSection, list[Statement]], int]:
    out, n = {}, 0
    for sec, stmts in narrative.items():
        done = [complete_identifier_citations(s, bundle, LLM_SECTIONS) for s in stmts]
        n += sum(len(d.added_fact_ids) for d in done)
        out[sec] = done
    return out, n


class ExplanationGeneratorAgent:
    """Agent 5. ``llm_client="auto"`` reads configuration from the environment;
    ``None`` forces the template writer; any object with ``complete_json`` is used as the LLM."""

    def __init__(self, llm_client: Union[LLMClient, None, str] = _AUTO, max_attempts: int = 2) -> None:
        self._llm = client_from_env() if llm_client == _AUTO else llm_client
        self._max_attempts = max(1, max_attempts)

    @property
    def llm_enabled(self) -> bool:
        return self._llm is not None

    def __call__(self, state: dict) -> dict:
        state["agent5_output"] = self.generate(state)
        return state

    def generate(self, state: dict, bundle: Optional[EvidenceBundle] = None,
                 force_template: bool = False) -> Agent5Output:
        """Write the report. ``bundle`` reuses an existing evidence bundle;
        ``force_template`` skips the LLM (used for the validation fallback)."""
        try:
            report = self._generate(state, bundle, force_template)
            source = getattr(state.get("transaction"), "source_dataset", None)
            if str(getattr(source, "value", source)) == "UPLOADED_DATASET":
                report = report.model_copy(update={"report_note": UPLOAD_REPORT_NOTE})
            return report
        except Exception as exc:  # noqa: BLE001
            logger.error("Agent 5 failed: %s", type(exc).__name__)
            tx = state.get("transaction")
            return Agent5Output(
                case_id=state.get("case_id"),
                transaction_id=getattr(tx, "raw_record_id", None),
                status=Agent5Status.FAILED,
                errors=[f"Report generation failed: {type(exc).__name__}"],
                decision=decision_from_agent4(state.get("agent4_output")),
            )

    def _generate(self, state: dict, bundle: Optional[EvidenceBundle] = None,
                  force_template: bool = False) -> Agent5Output:
        bundle = bundle if bundle is not None else build_evidence_bundle(state)
        llm = None if force_template else self._llm
        warnings: list[str] = []
        if bundle.missing_inputs:
            warnings.append("Missing upstream outputs: " + ", ".join(bundle.missing_inputs))

        narrative: Optional[dict[ReportSection, list[Statement]]] = None
        attempts, fallback_reason = 0, None
        if llm is not None:
            system, user = build_messages(bundle)
            prompt_user = user
            for _ in range(self._max_attempts):
                attempts += 1
                try:
                    text = llm.complete_json(system, prompt_user, schema=RESPONSE_SCHEMA)
                    narrative, w = parse_llm_output(text, bundle)
                    warnings.extend(w)
                    narrative, n_added = _complete_citations(narrative, bundle)
                    if n_added:
                        warnings.append(f"{n_added} identifier citation(s) added by code to LLM statements "
                                        "(recorded in added_fact_ids).")
                    fallback_reason = None
                    break
                except LLMGenerationError as exc:
                    fallback_reason = str(exc)  # model produced invalid output: ask again
                except LLMUnavailable as exc:
                    fallback_reason = str(exc)
                    break  # transport / auth / quota problems are not fixed by re-asking
                except LLMOutputError as exc:
                    fallback_reason = str(exc)
                    prompt_user = (user + "\n\nYour previous answer was rejected: " + str(exc)
                                   + ". Return the corrected JSON object only.")
            if narrative is None:
                warnings.append(f"LLM output not used ({fallback_reason}); template writer used.")

        generator = Generator.LLM if narrative is not None else Generator.TEMPLATE
        if narrative is None:
            narrative = template_narrative(bundle)

        if bundle.missing_inputs:
            status = Agent5Status.PARTIAL
        elif generator == Generator.LLM:
            status = Agent5Status.COMPLETE
        elif llm is not None:
            status = Agent5Status.FALLBACK_TEMPLATE
        else:
            status = Agent5Status.TEMPLATE

        return Agent5Output(
            case_id=bundle.case_id,
            transaction_id=bundle.transaction_id,
            status=status,
            generator=generator,
            llm_provider=getattr(llm, "provider", None) if llm is not None else None,
            llm_model=getattr(llm, "model", None) if llm is not None else None,
            llm_attempts=attempts,
            fallback_reason=fallback_reason if generator == Generator.TEMPLATE else None,
            prompt_version=PROMPT_VERSION if attempts else None,
            template_version=TEMPLATE_VERSION,
            warnings=warnings,
            sections=assemble_sections(bundle, narrative),
            decision=decision_from_agent4(state.get("agent4_output")),
            evidence_bundle=bundle,
        )
