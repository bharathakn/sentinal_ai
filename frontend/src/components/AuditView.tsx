import { formatDateTime, humanize } from "../lib/format";
import type { AuditEvent, TraceRecord } from "../lib/types";
import { Badge } from "./ui";

const DETAIL_KEYS = ["action", "rationale", "recommended_action", "risk_score", "validation_status", "pipeline_status",
  "report_generator", "system_recommended_action", "report_validation_status", "source", "transaction_id",
  "halt_reason", "error", "reason", "supersedes_decision_id"];

export function AuditView({ events }: { events: AuditEvent[] }) {
  return (
    <ol className="timeline">
      {events.map((e) => (
        <li key={e.event_id}>
          <div className="timeline-head">
            <strong>{humanize(e.event_type)}</strong>
            <span className="muted"> · {e.actor === "system" ? "System" : e.actor} · {formatDateTime(e.at_utc)}</span>
          </div>
          <div className="small muted">
            {DETAIL_KEYS.filter((k) => e.details[k] !== undefined && e.details[k] !== null && e.details[k] !== "")
              .map((k) => `${humanize(k)}: ${String(e.details[k])}`).join(" · ")}
          </div>
        </li>
      ))}
    </ol>
  );
}

export function PipelineView({ trace, status, halt }: { trace: TraceRecord[]; status?: string; halt?: string | null }) {
  return (
    <div>
      <p>Pipeline status: <Badge tone={status === "COMPLETE" ? "ok" : "warn"}>{status ?? "—"}</Badge></p>
      {halt && <p className="note note-warn">{halt}</p>}
      <table className="table compact">
        <thead><tr><th>Step</th><th>Outcome</th><th>Agent status</th><th className="num">Duration</th></tr></thead>
        <tbody>
          {trace.map((t, i) => (
            <tr key={i}>
              <td>{humanize(t.node)}</td>
              <td><Badge tone={t.outcome === "OK" ? "ok" : "critical"}>{t.outcome}</Badge>{t.error && <span className="small muted"> {t.error}</span>}</td>
              <td>{t.output_status ?? "—"}</td>
              <td className="num">{t.duration_ms.toFixed(0)} ms</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
