import { useState, type FormEvent } from "react";
import { api } from "../lib/api";
import { actionTone, formatDateTime, humanize } from "../lib/format";
import { ANALYST_ACTIONS, type AnalystAction, type CaseRecord } from "../lib/types";
import { Badge, Panel } from "./ui";

const HELP: Record<AnalystAction, string> = {
  BLOCK: "Stop the transaction / account activity",
  ESCALATE: "Refer for further investigation",
  MONITOR: "Allow, with enhanced monitoring",
  CLEAR: "No further action",
};

export function DecisionPanel({ record, onDecided }: { record: CaseRecord; onDecided: (r: CaseRecord) => void }) {
  const decidable = record.status === "AWAITING_REVIEW" || record.status === "DECIDED";
  const current = record.analyst_decision;
  const [action, setAction] = useState<AnalystAction | null>(null);
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revising, setRevising] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!action) return;
    setBusy(true);
    setError(null);
    try {
      onDecided(await api.decide(record.case_id, action, rationale.trim()));
      setAction(null);
      setRationale("");
      setRevising(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not record the decision.");
    } finally {
      setBusy(false);
    }
  }

  const showForm = decidable && (!current || revising);
  const recommended = record.summary.recommended_action;

  return (
    <Panel title="Analyst decision" className="decision">
      {!decidable && <p className="muted">A decision can be recorded once the investigation is complete.</p>}
      {current && (
        <div className="current-decision">
          <div><Badge tone={actionTone(current.action)}>{current.action}</Badge>{" "}
            by <strong>{current.analyst_name ?? current.analyst_id}</strong>{" "}
            <span className="muted">{formatDateTime(current.decided_at_utc)}</span></div>
          <p className="rationale">“{current.rationale}”</p>
          {current.agrees_with_system === false && (
            <p className="small muted">Differs from the system recommendation ({current.system_recommended_action}).</p>
          )}
          {!revising && decidable && <button className="btn btn-ghost" onClick={() => setRevising(true)}>Revise decision</button>}
        </div>
      )}
      {showForm && (
        <form onSubmit={submit} className="decision-form">
          {recommended && <p className="small muted">System recommendation: <strong>{humanize(recommended)}</strong>. The decision is yours.</p>}
          {record.summary.requires_human_review && (
            <p className="note note-warn small">Review the evidence carefully: this case is flagged for human review.</p>
          )}
          <div className="action-grid" role="radiogroup" aria-label="Decision">
            {ANALYST_ACTIONS.map((a) => (
              <button type="button" key={a} role="radio" aria-checked={action === a}
                      className={`action-btn action-${actionTone(a)} ${action === a ? "selected" : ""}`}
                      onClick={() => setAction(a)}>
                <strong>{humanize(a)}</strong><span>{HELP[a]}</span>
              </button>
            ))}
          </div>
          <label>
            Rationale <span className="muted">(recorded in the audit trail)</span>
            <textarea value={rationale} onChange={(e) => setRationale(e.target.value)} rows={3} maxLength={4000} required
                      placeholder="What in the evidence supports this decision?" />
          </label>
          {error && <div className="note note-error" role="alert">{error}</div>}
          <div className="row">
            <button className="btn btn-primary" disabled={busy || !action || !rationale.trim()}>
              {busy ? "Recording…" : action ? `Confirm ${humanize(action).toLowerCase()}` : "Choose an action"}
            </button>
            {revising && <button type="button" className="btn btn-ghost" onClick={() => setRevising(false)}>Cancel</button>}
          </div>
        </form>
      )}
      {record.decisions.length > 1 && (
        <details className="history">
          <summary>Decision history ({record.decisions.length})</summary>
          <ol>
            {[...record.decisions].reverse().map((d) => (
              <li key={d.decision_id}>
                <Badge tone={actionTone(d.action)}>{d.action}</Badge> {d.analyst_name ?? d.analyst_id} ·{" "}
                <span className="muted">{formatDateTime(d.decided_at_utc)}</span> — {d.rationale}
              </li>
            ))}
          </ol>
        </details>
      )}
    </Panel>
  );
}
