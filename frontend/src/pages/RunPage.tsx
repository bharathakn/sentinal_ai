import { useState } from "react";
import { Icon, STAGE_ICONS } from "../components/Icons";
import { RunReport } from "../components/live/RunReport";
import { AssessScene, DetectScene, ExplainScene, GatherScene, TraceScene, Working } from "../components/live/Scenes";
import { ScreeningScene } from "../components/live/ScreeningScene";
import { ActionBadge, ErrorNote, Spinner } from "../components/ui";
import { formatAmount } from "../lib/format";
import { QuickMotion } from "../lib/motion";
import { navigate } from "../lib/router";
import { STAGES, currentStage, stageState, type LiveCase, type StageState } from "../lib/run";
import { useRunPlayer } from "../lib/useRunPlayer";

const STATE_LABEL: Record<StageState, string> = {
  idle: "Waiting", running: "Working", done: "Done", error: "Needs review", skipped: "Skipped",
};

export function RunPage({ runId }: { runId: string }) {
  const { run, status, error, caughtUp } = useRunPlayer(runId);
  // What the analyst clicked; null follows the agents.
  const [pick, setPick] = useState<{ caseId: string; stage: number | null } | null>(null);

  const { phase, screening, cases } = run;
  const live = cases[cases.length - 1] as LiveCase | undefined;
  const active = (pick && cases.find((c) => c.id === pick.caseId)) || live;
  const stage = active ? (pick?.stage ?? currentStage(active)) : 0;
  const complete = phase === "complete";
  const showReport = complete && !pick;

  if (phase === "waiting" && error) {
    return <><ErrorNote>{error}</ErrorNote><button className="btn" onClick={() => navigate("/")}>Back to start</button></>;
  }
  // A run killed by a restart has no run.failed event: its log just ends.
  if (status === "FAILED" && (phase === "failed" || caughtUp)) {
    return (
      <div className="run">
        <h1 className="headline">This investigation did not finish.</h1>
        <ErrorNote>{run.error ? `It stopped with ${run.error}.` : "The service restarted while it was running."} Start it again.</ErrorNote>
        <button className="btn btn-primary" onClick={() => navigate("/")}>Back to start</button>
      </div>
    );
  }

  const states: StageState[] = STAGES.map((_, i) =>
    showReport ? (cases.length ? "done" : i === 0 ? "done" : "skipped")
      : phase === "screening" ? (i === 0 ? "running" : "idle")
      : stageState(active, i));

  const title = phase === "waiting" ? "Waking the agents…"
    : phase === "screening"
      ? screening.done ? "Found the ones worth investigating." : `Screening ${screening.total.toLocaleString("en-IN")} transactions…`
      : `${STAGES[stage].verb}${states[stage] === "running" ? "…" : "."}`;

  // Later cases move faster while following live; anything the analyst clicks animates normally.
  const quick = !complete && !pick && (active?.rank ?? 1) > 1;

  return (
    <div className="run">
      <div className="run-bar no-print">
        <p className="eyebrow">
          {!complete && <i className="live-dot" />}
          {complete ? "Investigation complete" : "Live investigation"}
          {run.dataset && ` · ${run.dataset.name}`}
        </p>
        <div className="run-controls">
          {complete ? (
            <>
              {pick && <button className="btn btn-primary" onClick={() => setPick(null)}>Back to final report</button>}
              <button className="btn btn-ghost" onClick={() => navigate("/")}>New investigation</button>
            </>
          ) : (
            pick && <button className="btn btn-primary" onClick={() => setPick(null)}>Follow live</button>
          )}
        </div>
      </div>

      {!showReport && <h1 className="headline run-title" key={title}>{title}</h1>}

      <ol className={`rail ${showReport ? "rail-small no-print" : ""}`} aria-label="The five agents">
        {STAGES.map((s, i) => (
          <li key={s.name} className={`station st-${states[i]} ${!showReport && active && i === stage ? "st-focus" : ""}`}>
            {i > 0 && <span className="track"><i /></span>}
            <button disabled={!active || showReport || states[i] === "idle"}
                    onClick={() => active && setPick({ caseId: active.id, stage: i })}>
              <span className="orb"><Icon name={STAGE_ICONS[i]} size={showReport ? 18 : 24} /></span>
              <strong>{s.name}</strong>
              <small>{s.agent}</small>
              <em>{STATE_LABEL[states[i]]}</em>
            </button>
          </li>
        ))}
      </ol>

      {error && <p className="note note-warn">{error}</p>}

      {showReport ? (
        <RunReport run={run} onWatch={(caseId) => setPick({ caseId, stage: 0 })} />
      ) : phase === "waiting" ? (
        <div className="theatre"><Working label="Queuing the dataset" /></div>
      ) : !active ? (
        <div className="theatre"><ScreeningScene s={screening} /></div>
      ) : (
        <>
          <div className="case-strip" aria-label="Transactions under investigation">
            {screening.selected.map((tx, i) => {
              const c = cases.find((x) => x.rank === i + 1);
              return (
                <button key={tx.transaction_id} disabled={!c}
                        className={`strip-card ${c?.id === active.id ? "strip-active" : ""} ${c ? "" : "strip-waiting"}`}
                        onClick={() => c && setPick(c === live && !complete ? null : { caseId: c.id, stage: null })}>
                  <span title={tx.lead ?? undefined}>{tx.lead ?? `Case ${i + 1}`}</span>
                  <strong>{formatAmount(tx.amount, tx.currency)}</strong>
                  {c?.done ? <ActionBadge action={c.summary?.recommended_action} /> : <small>{c ? "Investigating…" : "In the queue"}</small>}
                </button>
              );
            })}
          </div>
          <QuickMotion.Provider value={quick}>
          <section className={`theatre ${quick ? "theatre-quick" : ""}`} key={`${active.id}-${stage}`}>
            <header className="theatre-head">
              <span className="numeral">{stage + 1}</span>
              <div>
                <strong>{STAGES[stage].agent}</strong>
                <small>{active.tx.transaction_id} · {active.tx.sender} → {active.tx.receiver}</small>
              </div>
              <AgentTime c={active} stage={stage} />
            </header>
            <Scene c={active} stage={stage} />
          </section>
          </QuickMotion.Provider>
        </>
      )}
      {!complete && phase !== "waiting" && (
        <p className="fineprint centred">Live results from each agent</p>
      )}
    </div>
  );
}

function AgentTime({ c, stage }: { c: LiveCase; stage: number }) {
  const steps = STAGES[stage].nodes.map((n) => c.steps[n]).filter((s) => s?.ms !== undefined);
  if (!steps.length) return <Spinner label="Working" />;
  const ms = steps.reduce((total, s) => total + (s?.ms ?? 0), 0);
  return <span className="pill pill-soft">Actual time {ms < 1000 ? `${Math.max(1, Math.round(ms))} ms` : `${(ms / 1000).toFixed(1)} s`}</span>;
}

function Scene({ c, stage }: { c: LiveCase; stage: number }) {
  if (stageState(c, stage) === "skipped") {
    return <p className="note note-warn">Skipped: there was no risk score, so the case went straight to human review.</p>;
  }
  switch (stage) {
    case 0: return <DetectScene step={c.steps.anomaly_detector} />;
    case 1: return <GatherScene step={c.steps.evidence_gatherer} />;
    case 2: return <TraceScene step={c.steps.network_analyser} />;
    case 3: return <AssessScene step={c.steps.risk_assessor} />;
    default: return <ExplainScene draft={c.steps.explanation_generator} check={c.steps.output_validator} />;
  }
}
