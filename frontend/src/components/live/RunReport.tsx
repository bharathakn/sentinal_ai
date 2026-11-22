import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { actionTone, formatAmount, formatDateTime, formatScore, humanize } from "../../lib/format";
import { useCountUp } from "../../lib/motion";
import type { LiveCase, LiveRun } from "../../lib/run";
import { ANALYST_ACTIONS, type AnalystAction, type AnalystDecision } from "../../lib/types";
import { ActionBadge, Badge, ScoreBar, ValidationBadge } from "../ui";

const RECOMMEND: Record<string, string> = {
  BLOCK: "blocking it", ESCALATE: "escalating it", MONITOR: "monitoring it", CLEAR: "clearing it", HUMAN_REVIEW: "a human review",
};

type Decisions = Record<string, AnalystDecision | null>;

export function RunReport({ run, onWatch }: { run: LiveRun; onWatch: (caseId: string) => void }) {
  const [decisions, setDecisions] = useState<Decisions>({});
  const [open, setOpen] = useState<string | null>(run.cases[0]?.id ?? null);
  const ids = run.cases.map((c) => c.id).join(",");

  useEffect(() => {
    let alive = true;
    for (const id of ids ? ids.split(",") : []) {
      api.getCase(id)
        .then((rec) => alive && setDecisions((d) => ({ ...d, [id]: rec.analyst_decision })))
        .catch((e) => console.warn(`Decision state of ${id} could not be loaded`, e));
    }
    return () => { alive = false; };
  }, [ids]);

  const r = run.result;
  if (!r) return null;
  const resolved = run.cases.filter((c) => decisions[c.id]).length;
  const patterns = new Set(run.screening.selected.map((t) => t.lead).filter(Boolean)).size;

  return (
    <article className="final">
      <header className="final-head">
        <div>
          <p className="eyebrow">Final report · {run.dataset?.name}</p>
          <h1 className="headline">
            {r.investigated === 0 ? "Nothing here needed an investigation."
              : `${r.investigated} suspicious transaction${r.investigated === 1 ? "" : "s"}, fully investigated.`}
          </h1>
          <p className="lede">
            {r.screened.toLocaleString("en-IN")} transactions were screened and {r.flagged.toLocaleString("en-IN")} looked
            unusual to a model.{" "}
            {run.screening.varied && patterns === r.investigated
              ? `The strongest example of each of ${patterns} different suspected patterns went through all five agents.`
              : run.screening.varied
                ? `${r.investigated} went through all five agents: the strongest example of each of ${patterns} suspected patterns, then the next strongest signals.`
                : `The strongest ${r.investigated} went through all five agents.`}
            {r.not_investigated > 0 && ` The other ${r.not_investigated.toLocaleString("en-IN")} flagged transactions were not investigated in this run.`}
            {" "}Flagged means unusual, not proven fraud.
          </p>
        </div>
        <button className="btn no-print" onClick={() => window.print()}>Save as PDF</button>
      </header>

      <div className="kpis">
        <Kpi n={r.screened} label="Screened" />
        <Kpi n={r.flagged} label="Flagged" tone="amber" />
        <Kpi n={(r.by_action.BLOCK ?? 0) + (r.by_action.ESCALATE ?? 0)} label="Block or escalate" tone="red" />
        <Kpi n={r.validated} label="Reports validated" of={r.investigated} tone="green" />
      </div>

      {run.dataset && run.dataset.rejected_rows > 0 && (
        <details className="note note-warn">
          <summary>{run.dataset.rejected_rows.toLocaleString("en-IN")} rows could not be read and were left out</summary>
          <ul>{run.dataset.row_errors.map((e) => <li key={e}>{e}</li>)}</ul>
        </details>
      )}
      {run.dataset?.kind === "UPLOAD" && (
        <p className="note note-info">
          No bank records are connected for uploaded files, so those checks show as not connected. The models and the
          risk policy were calibrated on synthetic data: treat these results as a demonstration.
        </p>
      )}

      {run.cases.length > 0 && (
        <div className="resolve-head">
          <h2>Findings to resolve</h2>
          <div className="resolve-progress">
            <span>{resolved} of {run.cases.length} resolved</span>
            <span className="progress"><i style={{ width: `${(resolved / run.cases.length) * 100}%` }} /></span>
          </div>
        </div>
      )}

      <ol className="findings-list">
        {run.cases.map((c, i) => (
          <Finding key={c.id} c={c} index={i} open={open === c.id} decision={decisions[c.id] ?? null}
                   onToggle={() => setOpen(open === c.id ? null : c.id)} onWatch={() => onWatch(c.id)}
                   onDecided={(d) => setDecisions((all) => ({ ...all, [c.id]: d }))} />
        ))}
      </ol>
      <p className="fineprint">
        Prototype with mock bank services. Recommendations come from a deterministic risk policy; the AI only writes
        the explanation, and that is checked before it is shown as validated.
      </p>
    </article>
  );
}

function Kpi({ n, label, of, tone = "" }: { n: number; label: string; of?: number; tone?: string }) {
  const value = useCountUp(n, 1100);
  return (
    <div className={`kpi ${tone ? `kpi-${tone}` : ""}`}>
      <strong>{Math.round(value).toLocaleString("en-IN")}{of !== undefined && <small> / {of}</small>}</strong>
      <span>{label}</span>
    </div>
  );
}

function Finding({ c, index, open, decision, onToggle, onWatch, onDecided }: {
  c: LiveCase; index: number; open: boolean; decision: AnalystDecision | null;
  onToggle: () => void; onWatch: () => void; onDecided: (d: AnalystDecision | null) => void;
}) {
  const risk = c.steps.risk_assessor?.view;
  const network = c.steps.network_analyser?.view;
  const check = c.steps.output_validator?.view;
  const sections = check?.sections ?? c.steps.explanation_generator?.view?.sections ?? [];
  // The AI's own words when it wrote the (checked) report; otherwise the Risk Assessor's values in plain words.
  const aiWords = c.summary?.validation_status === "VALIDATED"
    ? sections.filter((s) => /network analysis/i.test(s.title))
        .flatMap((s) => s.statements.filter((x) => x.origin === "LLM").slice(0, 1))
    : [];
  const patterns = [...new Set(network?.findings.map((f) => humanize(f.pattern_type)) ?? [])];
  const signals = (risk?.signals ?? [])
    .filter((s) => s.available && (s.value ?? 0) > 0)
    .sort((a, b) => b.weight * (b.value ?? 0) - a.weight * (a.value ?? 0));

  return (
    <li className={`finding-card rise ${open ? "finding-open" : ""}`} style={{ animationDelay: `${index * 0.1}s` }}>
      <button className="finding-row" onClick={onToggle} aria-expanded={open}>
        <span className="numeral">{c.rank}</span>
        <span className="finding-tx">
          <strong>{formatAmount(c.tx.amount, c.tx.currency)}{c.tx.lead && <em className="lead-tag">{c.tx.lead}</em>}</strong>
          <small>{c.tx.sender} → {c.tx.receiver}</small>
        </span>
        <span className="finding-score"><ScoreBar score={c.summary?.risk_score} bandAction={c.summary?.score_band_action} /></span>
        <ActionBadge action={c.summary?.recommended_action} />
        <span className={`finding-state ${decision ? "is-resolved" : ""}`}>{decision ? `Resolved: ${humanize(decision.action)}` : "Needs your decision"}</span>
      </button>
      <div className="finding-body" hidden={!open}>
        <div className="why">
          <div>
            <h4>What drove the risk</h4>
            <ul className="why-list">
              {signals.slice(0, 4).map((s) => (
                <li key={s.signal}>
                  <strong>{humanize(s.signal)}</strong>
                  <span className="bar"><i style={{ width: `${(s.value ?? 0) * 100}%` }} /></span>
                  <span>{(s.value ?? 0).toFixed(2)}</span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h4>What the money did</h4>
            <div className="chips">
              {patterns.length ? patterns.map((p) => <Badge key={p} tone="medium">{p}</Badge>) : <span className="muted">No suspicious pattern found</span>}
            </div>
            <p className="small muted">{c.tx.channel} · {formatDateTime(c.timestamp)} · risk {formatScore(risk?.risk_score)}</p>
          </div>
        </div>
        {risk && (
          <div className="conclusion">
            <h4>Conclusion <ValidationBadge status={c.summary?.validation_status} /></h4>
            <p>
              The agents recommend <strong>{RECOMMEND[risk.recommended_action] ?? humanize(risk.recommended_action).toLowerCase()}</strong>
              {risk.risk_score !== null && `, with a risk score of ${formatScore(risk.risk_score)} out of 100`}
              {` and ${risk.confidence.toLowerCase()} confidence.`}
              {risk.sar_recommendation?.recommended && " A suspicious transaction report is recommended. Filing one is a human decision."}
            </p>
            {aiWords.map((s, i) => <p key={i}>{s.text}</p>)}
          </div>
        )}
        {c.status === "INVESTIGATION_FAILED"
          ? <p className="note note-error">This investigation did not finish.</p>
          : <Resolve caseId={c.id} recommended={c.summary?.recommended_action ?? null} decision={decision} onDecided={onDecided} />}
        <div className="finding-links no-print">
          <a className="btn" href={`#/cases/${c.id}`}>Open full report</a>
          <button className="btn btn-ghost" onClick={onWatch}>See each agent's work</button>
        </div>
      </div>
    </li>
  );
}

function Resolve({ caseId, recommended, decision, onDecided }: {
  caseId: string; recommended: string | null; decision: AnalystDecision | null; onDecided: (d: AnalystDecision | null) => void;
}) {
  const [action, setAction] = useState<AnalystAction | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (decision) {
    return (
      <div className="resolved rise">
        <Badge tone={actionTone(decision.action)}>{humanize(decision.action)}</Badge>
        <span>by {decision.analyst_name ?? decision.analyst_id}: “{decision.rationale}”</span>
      </div>
    );
  }

  async function confirm() {
    if (!action) return;
    setBusy(true);
    setError(null);
    try {
      onDecided((await api.decide(caseId, action, reason.trim())).analyst_decision);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not record the decision.");
      setBusy(false);
    }
  }

  return (
    <div className="resolve no-print">
      <h4>Resolve{recommended && <span className="muted"> · the agents recommend {RECOMMEND[recommended] ?? humanize(recommended).toLowerCase()}</span>}</h4>
      <div className="resolve-actions" role="radiogroup" aria-label="Decision">
        {ANALYST_ACTIONS.map((a) => (
          <button key={a} role="radio" aria-checked={action === a}
                  className={`choice action-${actionTone(a)} ${action === a ? "selected" : ""}`} onClick={() => setAction(a)}>
            {humanize(a)}
          </button>
        ))}
      </div>
      {action && (
        <div className="resolve-confirm rise">
          <input autoFocus value={reason} maxLength={4000} aria-label="Reason" onChange={(e) => setReason(e.target.value)}
                 placeholder="Reason, recorded in the audit trail" />
          <button className="btn btn-primary" disabled={busy || !reason.trim()} onClick={confirm}>
            {busy ? "Saving…" : `Confirm ${humanize(action).toLowerCase()}`}
          </button>
        </div>
      )}
      {error && <div className="note note-error" role="alert">{error}</div>}
    </div>
  );
}
