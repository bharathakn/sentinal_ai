import { useMemo, useState } from "react";
import { api } from "../lib/api";
import { formatDateTime, humanize } from "../lib/format";
import type { Fact, RegulatoryMatch, Report, Validation } from "../lib/types";
import { Badge, ValidationBadge } from "./ui";

export function FactCard({ fact, onClose }: { fact: Fact; onClose?: () => void }) {
  return (
    <div className="fact-card" role="dialog" aria-label={`Evidence ${fact.fact_id}`}>
      <div className="fact-head">
        <strong>{fact.fact_id}</strong> <span>{fact.label}</span>
        {onClose && <button className="btn btn-ghost btn-xs" onClick={onClose} aria-label="Close">×</button>}
      </div>
      <div className="fact-value">{fact.value}</div>
      <div className="fact-meta">
        <span>Source: <strong>{fact.source}</strong></span>
        <span>Agent: {humanize(fact.source_agent)}</span>
        {fact.source_mode && <Badge tone={fact.source_mode === "LIVE" ? "neutral" : "warn"}>{fact.source_mode}</Badge>}
        {fact.observed_at && <span>Observed {formatDateTime(fact.observed_at)}</span>}
        <span className="mono small">{fact.source_field}</span>
      </div>
    </div>
  );
}

export function ReportView({ caseId, report, validation, rejectedCount, regulatory }: {
  caseId: string; report: Report; validation: Validation | undefined; rejectedCount: number;
  regulatory: RegulatoryMatch[];
}) {
  const facts = useMemo(() => new Map((report.evidence_bundle?.facts ?? []).map((f) => [f.fact_id, f])), [report]);
  const [open, setOpen] = useState<{ key: string; fact: Fact } | null>(null);

  return (
    <div className="report">
      <div className="report-meta">
        <ValidationBadge status={report.validation_status} />
        <span className="muted">
          Written by {report.generator === "LLM" ? `LLM (${report.llm_model})` : "template writer"}
          {report.status === "FALLBACK_TEMPLATE" && " — LLM report failed validation and was replaced"}
        </span>
        <a className="btn btn-ghost btn-xs" href={api.reportMarkdownUrl(caseId)} target="_blank" rel="noreferrer">Markdown</a>
      </div>
      <p className="note note-info small">{report.report_note}</p>
      {report.validation_status !== "VALIDATED" && (
        <div className="note note-warn">This report is NOT validated. Treat its narrative with caution and rely on the cited evidence.</div>
      )}
      {validation && <ValidationSummary v={validation} rejectedCount={rejectedCount} />}
      {report.sections.map((sec) => (
        <section key={sec.section} className="report-section">
          <h3>{sec.title}</h3>
          {sec.statements.length === 0 && <p className="muted">Not identified</p>}
          <ul>
            {sec.statements.map((st, i) => (
              <li key={i} className={`statement origin-${st.origin.toLowerCase()}`}>
                <span>{st.text}</span>{" "}
                <span className="cites">
                  {st.fact_ids.map((id) => {
                    const key = `${sec.section}-${i}-${id}`;
                    const f = facts.get(id);
                    return (
                      <button key={id} className={`cite ${open?.key === key ? "cite-open" : ""}`}
                              title={f ? `${f.label}: ${f.value}` : id}
                              onClick={() => f && setOpen(open?.key === key ? null : { key, fact: f })}>
                        {id}
                      </button>
                    );
                  })}
                </span>
                {st.origin !== "LLM" && <span className="origin-tag">{st.origin.toLowerCase()}</span>}
                {open && open.key.startsWith(`${sec.section}-${i}-`) && <FactCard fact={open.fact} onClose={() => setOpen(null)} />}
              </li>
            ))}
          </ul>
          {sec.section === "REGULATORY_ASSESSMENT" && regulatory.length > 0 && <RegulatoryList matches={regulatory} />}
        </section>
      ))}
    </div>
  );
}

function ValidationSummary({ v, rejectedCount }: { v: Validation; rejectedCount: number }) {
  return (
    <details className="validation" open={v.status !== "VALIDATED"}>
      <summary>
        Output Validator: <strong>{v.checks_passed}/{v.checks_total}</strong> checks passed
        {rejectedCount > 0 && <span className="muted"> · {rejectedCount} rejected report kept for audit</span>}
      </summary>
      <table className="table compact">
        <tbody>
          {v.checks.map((c) => (
            <tr key={c.check}>
              <td>{c.passed ? <Badge tone="ok">pass</Badge> : <Badge tone="critical">fail</Badge>}</td>
              <td><strong>{humanize(c.check)}</strong><div className="small muted">{c.description}</div>
                {c.issues.map((iss, j) => <div key={j} className="small issue">• {iss.reason}</div>)}
              </td>
              <td className="num small">{c.items_checked} items</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

function RegulatoryList({ matches }: { matches: RegulatoryMatch[] }) {
  const unique = matches.filter((m, i) => matches.findIndex((x) => x.reference_id === m.reference_id) === i);
  return (
    <div className="regulatory">
      {unique.map((m) => (
        <details key={m.reference_id} className="reg-item">
          <summary>
            <strong>{m.reference_id}</strong> {m.organization} — {m.section}{" "}
            <Badge tone="warn" title="Mapping not yet reviewed by a qualified person">{m.verification_status}</Badge>
          </summary>
          <p className="small"><em>{m.document_name}</em>{m.pdf_page ? `, p. ${m.pdf_page}` : ""}</p>
          <blockquote>{m.excerpt}</blockquote>
          <p className="small muted">Why it applies: {m.mapping_rationale}</p>
        </details>
      ))}
    </div>
  );
}
