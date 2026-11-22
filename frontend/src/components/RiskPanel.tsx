import { bandsFrom, formatScore, humanize } from "../lib/format";
import type { Agent4Output, CaseSummary } from "../lib/types";
import { ActionBadge, Badge, KeyValue, Panel, ValidationBadge } from "./ui";

export function RiskPanel({ a4, summary }: { a4: Agent4Output | undefined; summary: CaseSummary }) {
  if (!a4) return <Panel title="Risk assessment"><p className="muted">No risk assessment.</p></Panel>;
  const bands = bandsFrom(a4.config_snapshot ?? null);
  const score = a4.risk_score;
  return (
    <Panel title="Risk assessment" className="risk">
      <div className="risk-top">
        <div className="score-big" aria-label="Risk score">
          <span className="score-num">{formatScore(score)}</span>
          <span className="score-of">/ 100</span>
        </div>
        <div className="risk-labels">
          <div><span className="muted">Recommended action</span><ActionBadge action={a4.recommended_action} /></div>
          <div><span className="muted">Confidence</span><Badge>{humanize(a4.confidence)}</Badge></div>
          <div><span className="muted">Report</span><ValidationBadge status={summary.validation_status} /></div>
        </div>
      </div>
      {bands && score !== null && (
        <div className="bands" aria-hidden="true">
          {bands.map((b) => (
            <div key={b.label} className={`band band-${b.tone}`} style={{ flexGrow: b.to - b.from }}>
              <span>{b.label}</span>
            </div>
          ))}
          <div className="band-marker" style={{ left: `${Math.min(100, Math.max(0, score))}%` }} />
        </div>
      )}
      {summary.requires_human_review && (
        <div className="note note-warn">
          Human review required
          {summary.validation_status !== "VALIDATED" && " — the report did not pass validation"}
          {summary.pipeline_status && summary.pipeline_status !== "COMPLETE" && ` — pipeline ${summary.pipeline_status.toLowerCase()}`}.
        </div>
      )}
      {a4.overrides_applied.length > 0 && (
        <div className="overrides">
          {a4.overrides_applied.map((o) => (
            <div key={o.rule_id} className="note note-info">
              <strong>{o.rule_id}</strong> (at least {o.minimum_action}): {o.description}
            </div>
          ))}
        </div>
      )}
      <KeyValue items={[
        ["Score band action", a4.score_band_action ?? "—"],
        ["SAR/STR", a4.sar_recommendation.recommended
          ? <span><Badge tone="high">Recommended</Badge> <span className="muted">{a4.sar_recommendation.basis.join("; ")}</span></span>
          : <Badge tone="ok">Not recommended</Badge>],
        ["Evidence coverage", a4.evidence_coverage === null ? "—" : `${Math.round(a4.evidence_coverage * 100)}%`],
        ["Unavailable signals", a4.unavailable_signals.length ? a4.unavailable_signals.join(", ") : "None"],
        ["Confidence reasons", a4.confidence_reasons.join("; ") || "—"],
        ["Policy", `config ${a4.config_version ?? "?"} · mapping ${a4.mapping_version ?? "?"}`],
      ]} />
      <p className="fineprint">{a4.sar_recommendation.note}</p>
      <h3>Score breakdown</h3>
      <div className="table-wrap">
        <table className="table compact">
          <thead><tr><th>Signal</th><th className="num">Weight</th><th className="num">Value</th><th className="num" title="weight × value, as computed by the Risk Assessor">Weighted</th><th>Basis</th></tr></thead>
          <tbody>
            {a4.score_breakdown.map((c) => (
              <tr key={c.signal} className={c.available ? "" : "row-muted"}>
                <td>{humanize(c.signal)}</td>
                <td className="num">{c.weight.toFixed(2)}</td>
                <td className="num">{c.available && c.value !== null ? c.value.toFixed(2) : "n/a"}</td>
                <td className="num">{c.contribution === null ? "—" : c.contribution.toFixed(3)}</td>
                <td className="small">{c.rationale}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
