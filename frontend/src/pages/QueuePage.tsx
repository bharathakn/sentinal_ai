import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ActionBadge, Badge, ErrorNote, Panel, ScoreBar, Spinner, ValidationBadge } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { formatAmount, relativeTime, statusLabel } from "../lib/format";
import { navigate } from "../lib/router";
import type { CaseList } from "../lib/types";

const FILTERS: { key: string; label: string }[] = [
  { key: "AWAITING_REVIEW", label: "Awaiting review" },
  { key: "", label: "All cases" },
  { key: "DECIDED", label: "Decided" },
  { key: "INVESTIGATING", label: "In progress" },
  { key: "INVESTIGATION_FAILED", label: "Failed" },
];

export function QueuePage() {
  const [filter, setFilter] = useState("AWAITING_REVIEW");
  const [data, setData] = useState<CaseList | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.listCases({ status: filter || undefined, limit: 200 }));
      setError(null);
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 401)) setError(e instanceof Error ? e.message : "Failed to load cases");
    }
  }, [filter]);

  useEffect(() => {
    setData(null);
    load();
    const t = window.setInterval(load, 15000); // new alerts and finished investigations appear on their own
    return () => window.clearInterval(t);
  }, [load]);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Case queue</h1>
          <p className="muted">Most severe recommended action first, then highest risk score, then oldest.</p>
        </div>
        <NewAlert onCreated={load} />
      </div>
      <div className="tabs" role="tablist">
        {FILTERS.map((f) => (
          <button key={f.key} role="tab" aria-selected={filter === f.key}
                  className={`tab ${filter === f.key ? "tab-active" : ""}`} onClick={() => setFilter(f.key)}>
            {f.label}
          </button>
        ))}
      </div>
      <Panel>
        {error && <ErrorNote>{error}</ErrorNote>}
        {!data && !error && <Spinner label="Loading cases…" />}
        {data && data.items.length === 0 && <p className="empty">No cases here.</p>}
        {data && data.items.length > 0 && (
          <div className="table-wrap">
            <table className="table queue">
              <thead>
                <tr>
                  <th>Recommended</th><th>Risk score</th><th>Case</th><th>Transaction</th><th>Amount</th>
                  <th>Report</th><th>Status</th><th>Received</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((c) => (
                  <tr key={c.case_id} className="clickable" tabIndex={0}
                      onClick={() => navigate(`/cases/${c.case_id}`)}
                      onKeyDown={(e) => e.key === "Enter" && navigate(`/cases/${c.case_id}`)}>
                    <td><ActionBadge action={c.summary.recommended_action} /></td>
                    <td><ScoreBar score={c.summary.risk_score} bandAction={c.summary.score_band_action} /></td>
                    <td className="mono">{c.case_id}</td>
                    <td className="mono">{c.transaction_id ?? "—"}</td>
                    <td className="num">{formatAmount(c.amount, c.currency)}</td>
                    <td>
                      {c.status === "AWAITING_REVIEW" || c.status === "DECIDED"
                        ? <ValidationBadge status={c.summary.validation_status} /> : <span className="muted">—</span>}
                      {c.summary.pipeline_status === "HALTED" && <Badge tone="warn">Halted</Badge>}
                    </td>
                    <td>
                      {c.analyst_action
                        ? <span>Decided: <strong>{c.analyst_action}</strong></span>
                        : <span className={`status status-${c.status.toLowerCase()}`}>{statusLabel(c.status)}</span>}
                    </td>
                    <td className="muted" title={c.created_at_utc}>{relativeTime(c.created_at_utc)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && <p className="fineprint">{data.total} case{data.total === 1 ? "" : "s"} · {data.prototype_notice}</p>}
      </Panel>
    </div>
  );
}

function NewAlert({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [txId, setTxId] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.submitAlert(txId.trim());
      setMsg(r.duplicate ? `Already investigated as ${r.case_id}.` : `Case ${r.case_id} created; investigating…`);
      setTxId("");
      onCreated();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Could not submit the alert.");
    } finally {
      setBusy(false);
    }
  }

  if (!open) return <button className="btn" onClick={() => setOpen(true)}>Submit alert</button>;
  return (
    <form className="inline-form" onSubmit={submit}>
      <input placeholder="Synthetic transaction id, e.g. TXN_IND_202608_000977" value={txId}
             onChange={(e) => setTxId(e.target.value)} aria-label="Transaction id" pattern="[A-Za-z0-9_\-]+" required />
      <button className="btn btn-primary" disabled={busy}>{busy ? "Submitting…" : "Investigate"}</button>
      <button type="button" className="btn btn-ghost" onClick={() => { setOpen(false); setMsg(null); }}>Close</button>
      {msg && <span className="inline-msg">{msg}</span>}
    </form>
  );
}
