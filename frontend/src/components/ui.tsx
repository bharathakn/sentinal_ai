import type { ReactNode } from "react";
import { actionTone, humanize, validationTone, type Tone } from "../lib/format";

export function Badge({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return <span className={`badge badge-${tone}`} title={title}>{children}</span>;
}

export function ActionBadge({ action }: { action: string | null | undefined }) {
  return <Badge tone={actionTone(action)}>{action ? humanize(action) : "Pending"}</Badge>;
}

export function ValidationBadge({ status }: { status: string | null | undefined }) {
  const label = status === "VALIDATED" ? "Report validated"
    : status === "NEEDS_HUMAN_REVIEW" ? "Report not validated"
    : status === "NOT_VALIDATED" ? "Not validated" : "No report";
  return <Badge tone={validationTone(status)} title={status ?? undefined}>{label}</Badge>;
}

/** Score bar coloured by the score-band action Agent 4 assigned (no thresholds in the UI). */
export function ScoreBar({ score, bandAction }: { score: number | null | undefined; bandAction?: string | null }) {
  if (score === null || score === undefined) return <span className="muted">—</span>;
  const tone = actionTone(bandAction);
  return (
    <span className="scorebar" aria-label={`Risk score ${score.toFixed(2)}`}>
      <span className="scorebar-track"><span className={`scorebar-fill fill-${tone}`} style={{ width: `${Math.min(100, score)}%` }} /></span>
      <span className="scorebar-num">{score.toFixed(1)}</span>
    </span>
  );
}

export function Panel({ title, actions, children, className = "" }: {
  title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <header className="panel-head">
          {title && <h2>{title}</h2>}
          {actions && <div className="panel-actions">{actions}</div>}
        </header>
      )}
      <div className="panel-body">{children}</div>
    </section>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return <div className="spinner" role="status"><span className="spinner-dot" />{label}</div>;
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return <div className="note note-error" role="alert">{children}</div>;
}

export function KeyValue({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="kv">
      {items.map(([k, v], i) => (
        <div key={i} className="kv-row"><dt>{k}</dt><dd>{v}</dd></div>
      ))}
    </dl>
  );
}
