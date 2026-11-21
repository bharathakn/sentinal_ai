"""
Sentinel AI — Output Validator pipeline stage.

Runs after Agent 5. Validates the report, records the result on the state
(``validation_output``) and on the report (``validation_status``).

Fallback policy (decided in Phase 11):
  If an LLM-written report fails validation, a template report is written
  from the SAME evidence bundle and validated. If it passes, the template
  report is presented and the rejected LLM report is kept, with its failed
  checks, in ``rejected_reports`` for audit. If the template report also
  fails, the LLM report is presented as NEEDS_HUMAN_REVIEW.
  A failed report is never presented as validated.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..agent5.report_schema import Agent5Output, Agent5Status, Generator
from .output_validator import OutputValidator
from .schema import ReportReviewRecord, ValidationOutput, ValidationStatus

logger = logging.getLogger(__name__)


def _with_status(report: Agent5Output, v: ValidationOutput, extra_warning: Optional[str] = None) -> Agent5Output:
    warnings = list(report.warnings)
    if extra_warning:
        warnings.append(extra_warning)
    if v.analyst_warning:
        warnings.append(v.analyst_warning)
    return report.model_copy(update={"validation_status": v.status.value, "warnings": warnings})


class ValidationStage:
    """Callable pipeline node: state → state with validated / flagged report."""

    def __init__(self, validator: Optional[OutputValidator] = None, template_writer: Any = None,
                 template_fallback: bool = True) -> None:
        self.validator = validator or OutputValidator()
        self._template_writer = template_writer
        self.template_fallback = template_fallback

    def _writer(self):
        if self._template_writer is None:
            from ..agent5 import ExplanationGeneratorAgent
            self._template_writer = ExplanationGeneratorAgent(llm_client=None)
        return self._template_writer

    def __call__(self, state: dict) -> dict:
        report = state.get("agent5_output")
        v = self.validator.validate(state, report)
        rejected: list[ReportReviewRecord] = list(state.get("rejected_reports") or [])

        if (v.status == ValidationStatus.NEEDS_HUMAN_REVIEW and self.template_fallback
                and report is not None and report.generator == Generator.LLM
                and report.evidence_bundle is not None):
            tpl = self._writer().generate(state, bundle=report.evidence_bundle, force_template=True)
            tv = self.validator.validate(state, tpl)
            if tv.status == ValidationStatus.VALIDATED:
                reason = "LLM report failed validation (" + ", ".join(c.value for c in v.failed_checks()) + ")"
                rejected.append(ReportReviewRecord(reason=reason, report=_with_status(report, v), validation=v))
                tpl = tpl.model_copy(update={
                    "status": Agent5Status.FALLBACK_TEMPLATE,
                    "llm_provider": report.llm_provider, "llm_model": report.llm_model,
                    "llm_attempts": report.llm_attempts, "prompt_version": report.prompt_version,
                    "fallback_reason": reason,
                })
                logger.info("Case %s: %s; validated template report presented.", state.get("case_id"), reason)
                report, v = _with_status(tpl, tv, reason + "; template report presented, LLM report kept for audit."), tv
                state["agent5_output"] = report
                state["validation_output"] = v
                state["rejected_reports"] = rejected
                return state
            logger.info("Case %s: template report also failed validation.", state.get("case_id"))

        if report is not None:
            state["agent5_output"] = _with_status(report, v)
        state["validation_output"] = v
        state["rejected_reports"] = rejected
        return state
