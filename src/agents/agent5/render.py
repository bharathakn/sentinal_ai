"""Sentinel AI — Agent 5: Markdown rendering of a report (display only)."""

from __future__ import annotations

from .report_schema import Agent5Output, StatementOrigin


def render_markdown(report: Agent5Output, include_facts: bool = True, validation=None) -> str:
    """Render a report. ``validation`` (a validator ValidationOutput) adds the
    per-check validation results."""
    d = report.decision
    lines = [
        f"# Investigation Report — {report.case_id or 'Not identified'}",
        "",
        f"**Status:** {report.validation_status} · generator {report.generator.value if report.generator else 'none'}"
        + (f" ({report.llm_model})" if report.generator and report.generator.value == "LLM" else "")
        + f" · transaction {report.transaction_id or 'Not identified'}",
        "",
        f"> {report.report_note}",
        "",
        f"**Decision (from Risk Assessor):** {d.recommended_action or 'Not identified'} · risk score "
        f"{'Not identified' if d.risk_score is None else f'{d.risk_score:.2f}'} · SAR/STR "
        f"{'Not identified' if d.sar_recommended is None else ('recommended' if d.sar_recommended else 'not recommended')}",
        "",
    ]
    if report.warnings:
        lines += ["**Warnings:**"] + [f"- {w}" for w in report.warnings] + [""]
    if validation is not None:
        lines += [f"**Validation:** {validation.status.value} · {validation.checks_passed}/"
                  f"{validation.checks_total} checks passed (validator {validation.validator_version})", "",
                  "| Check | Result | Items | Issues |", "|---|---|---|---|"]
        for c in validation.checks:
            lines.append(f"| {c.check.value} | {'pass' if c.passed else '**FAIL**'} | {c.items_checked} | {len(c.issues)} |")
        lines.append("")
        for c in validation.checks:
            for i in c.issues:
                where = f"{i.section}[{i.statement_index}] " if i.section and i.statement_index is not None else ""
                lines.append(f"- {c.check.value}: {where}{i.reason}")
        lines.append("")
    for sec in report.sections:
        lines += [f"## {sec.title}", ""]
        if not sec.statements:
            lines += ["Not identified", ""]
        for s in sec.statements:
            tag = "" if s.origin == StatementOrigin.LLM else f" _({s.origin.value.lower()})_"
            lines.append(f"- {s.text} [{', '.join(s.fact_ids)}]{tag}")
        lines.append("")
    b = report.evidence_bundle
    if include_facts and b is not None:
        lines += [f"## Evidence facts ({len(b.facts)}; bundle sha256 {b.bundle_hash[:16]}…)", "",
                  "| Id | Fact | Value | Source |", "|---|---|---|---|"]
        for f in b.facts:
            val = f.value.replace("|", "\\|").replace("\n", " ")
            src = f.source + (f" ({f.source_mode})" if f.source_mode else "")
            lines.append(f"| {f.fact_id} | {f.label} | {val} | {src} |")
        lines.append("")
    return "\n".join(lines)
