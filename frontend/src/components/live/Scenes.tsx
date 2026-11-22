import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { fallbackNote, formatScore, humanize } from "../../lib/format";
import { prefersReducedMotion, useCountUp } from "../../lib/motion";
import type { AnomalyView, CheckView, DraftView, EvidenceProviders, DraftSection, RiskView, Step } from "../../lib/run";
import type { NetworkView } from "../../lib/types";
import { Icon } from "../Icons";
import { ActionBadge } from "../ui";
import { MoneyFlow } from "./MoneyFlow";

const delay = (seconds: number): CSSProperties => ({ animationDelay: `${seconds}s` });

const DRIVER_NAMES: Record<string, string> = {
  log_amount: "Transaction amount",
  amount_ratio_vs_30d_avg: "Amount vs. 30-day average",
  log_amount_ratio: "Amount spike",
  tx_frequency_24h: "Transfers in the last 24 hours",
  log_time_since_last_tx: "Time since previous transfer",
  balance_drain_ratio: "Share of balance drained",
  hour_of_day: "Hour of day",
  is_night: "Night-time transfer",
  day_of_week: "Day of week",
  channel_upi: "UPI channel",
  channel_neft: "NEFT channel",
  channel_rtgs: "RTGS channel",
};

function Failed({ step }: { step?: { error?: string | null } }) {
  return <p className="note note-warn">This step did not complete{step?.error ? ` (${step.error})` : ""}. The case is flagged for human review.</p>;
}

// 1 ─ Detect
export function DetectScene({ step }: { step?: Step<AnomalyView> }) {
  if (step?.state === "error") return <Failed step={step} />;
  if (!step?.view) return <Working label="Scoring the transaction with both models" />;
  return <Detected v={step.view} />;
}

function Detected({ v }: { v: AnomalyView }) {
  const confidence = v.combined_confidence ?? 0;
  const shown = useCountUp(confidence * 100, 1300);
  const max = Math.max(0.001, ...v.drivers.map((d) => Math.abs(d.shap_value)));
  return (
    <div className="scene detect">
      <div className="ring">
        <svg viewBox="0 0 180 180" aria-hidden="true">
          <circle cx="90" cy="90" r="76" className="ring-track" />
          <circle cx="90" cy="90" r="76" className="ring-value" pathLength={100} transform="rotate(-90 90 90)"
                  strokeDasharray={`${shown} 100`} />
        </svg>
        <div className="ring-label"><strong>{(shown / 100).toFixed(2)}</strong><span>anomaly signal</span></div>
      </div>
      <div>
        <div className="model-pair">
          <Model name="XGBoost" value={v.xgboost.fraud_probability} threshold={v.xgboost.threshold_used} />
          <Model name="Isolation Forest" value={v.isolation_forest.anomaly_score} threshold={v.isolation_forest.threshold_used} />
        </div>
        <h4>What drove the score</h4>
        <ul className="drivers">
          {v.drivers.map((d, i) => (
            <li key={d.feature} className="rise" style={delay(0.3 + i * 0.16)}>
              <span>{DRIVER_NAMES[d.feature] ?? humanize(d.feature)}</span>
              <span className="bar"><i className={d.shap_value < 0 ? "down" : ""}
                style={{ width: `${(Math.abs(d.shap_value) / max) * 100}%`, ...delay(0.35 + i * 0.16) }} /></span>
              <b>{d.shap_value >= 0 ? "+" : "−"}{Math.abs(d.shap_value).toFixed(2)}</b>
            </li>
          ))}
        </ul>
        <p className="fineprint">A heuristic blend of the two models. It is not a probability of fraud.</p>
      </div>
    </div>
  );
}

function Model({ name, value, threshold }: { name: string; value: number | null; threshold: number | null }) {
  const over = value !== null && threshold !== null && value >= threshold;
  return (
    <div className={`model rise ${over ? "model-over" : ""}`}>
      <span>{name}</span>
      <strong>{value === null ? "n/a" : value.toFixed(3)}</strong>
      <small>{threshold === null ? "" : `${over ? "above" : "below"} its ${threshold.toFixed(3)} threshold`}</small>
    </div>
  );
}

// 2 ─ Gather
const PROVIDERS: [RegExp, string][] = [
  [/core/, "Core banking"], [/kyc/, "KYC identity"], [/device/, "Device registry"], [/beneficiary/, "Beneficiary records"],
  [/sanctions.*subject/, "Sanctions: person"], [/sanctions.*account/, "Sanctions: account"], [/geo/, "Geolocation"], [/news/, "Adverse news"],
];

export function providerName(raw: string): string {
  return PROVIDERS.find(([re]) => re.test(raw.toLowerCase()))?.[1] ?? humanize(raw);
}

export function providerOutcome(status: string, error?: string | null): [string, string] {
  if (status === "FOUND") return ["Record found", "good"];
  if (status === "NO_MATCH") return ["No match", "good"];
  if (status === "NO_ARTICLES") return ["Nothing reported", "good"];
  if (status === "MATCH_FOUND") return ["Match found", "bad"];
  if (status === "NOT_FOUND") return ["No record", "quiet"];
  if (status === "VALIDATION_ERROR") return ["Nothing to check", "quiet"];
  if (error?.includes("NotConnected")) return ["Not connected", "quiet"];
  return ["Unavailable", "warn"];
}

export function GatherScene({ step }: { step?: Step<EvidenceProviders> }) {
  if (step?.state === "error") return <Failed step={step} />;
  const found = step?.view?.providers;
  // While Agent 2 runs its sources are pulsing; results appear only when it returns them.
  const order = (raw: string) => PROVIDERS.findIndex(([re]) => re.test(raw.toLowerCase()));
  const items = found
    ? [...found].sort((a, b) => order(a.name) - order(b.name))
    : PROVIDERS.map(([, name]) => ({ name, status: "", source_mode: null, error: null }));
  return (
    <div className="scene gather">
      {items.map((p, i) => {
        const [label, tone] = found ? providerOutcome(p.status, p.error) : ["Querying…", "busy"];
        return (
          <div key={`${found ? "r" : "q"}-${p.name}`} className={`source source-${tone} rise`} style={delay(i * (found ? 0.22 : 0.05))}>
            <span className="source-mark">
              {tone === "good" ? <Icon name="check" size={15} /> : tone === "bad" ? <Icon name="cross" size={15} /> : <i />}
            </span>
            <strong>{found ? providerName(p.name) : p.name}</strong>
            <span>{label}</span>
            {p.source_mode && <small>{p.source_mode.toLowerCase()} source</small>}
          </div>
        );
      })}
    </div>
  );
}

// 3 ─ Trace
export function TraceScene({ step }: { step?: Step<NetworkView> }) {
  if (step?.state === "error") return <Failed step={step} />;
  if (!step?.view) return <Working label="Walking the transfers around both accounts" />;
  const v = step.view;
  const groups = new Map<string, { count: number; text: string }>();
  for (const f of v.findings) {
    const g = groups.get(f.pattern_type);
    groups.set(f.pattern_type, { count: (g?.count ?? 0) + 1, text: g?.text ?? f.explanation });
  }
  return (
    <div className="scene trace">
      <MoneyFlow view={v} />
      <ul className="patterns">
        {groups.size === 0 && (
          <li className="rise">
            <strong>{v.agent3_status === "COMPLETE" ? "No suspicious pattern" : "Network evidence incomplete"}</strong>
            <p>{v.agent3_warnings[0] ?? "No known pattern around these accounts in the time window."}</p>
          </li>
        )}
        {[...groups].map(([name, g], i) => (
          <li key={name} className="rise" style={delay(0.7 + i * 0.35)} title={g.text}>
            <strong>{humanize(name)}{g.count > 1 && <em>×{g.count}</em>}</strong>
            <p>{g.text}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

// 4 ─ Assess
export function AssessScene({ step }: { step?: Step<RiskView> }) {
  if (step?.state === "error") return <Failed step={step} />;
  if (!step?.view) return <Working label="Combining seven signals" />;
  return <Assessed v={step.view} />;
}

const ARC = "M30,150 A120,120 0 0 1 270,150";

function Assessed({ v }: { v: RiskView }) {
  const score = useCountUp(v.risk_score ?? 0, 1700);
  const t = v.thresholds;
  const bands: [number, number, string][] = [
    [0, t.monitor_threshold, "ok"], [t.monitor_threshold, t.escalate_threshold, "low"],
    [t.escalate_threshold, t.block_threshold, "high"], [t.block_threshold, 100, "critical"],
  ];
  return (
    <div className="scene assess">
      <div className="gauge">
        <svg viewBox="0 0 300 172" aria-hidden="true">
          {bands.map(([from, to, tone]) => (
            <path key={tone} d={ARC} pathLength={100} className={`gauge-band gb-${tone}`}
                  strokeDasharray={`0 ${from} ${Math.max(0, to - from - 0.7)} 100`} />
          ))}
          <g transform={`rotate(${(score / 100) * 180 - 90} 150 150)`}>
            <path d="M146,150 L150,56 L154,150 z" className="needle" />
          </g>
          <circle cx="150" cy="150" r="9" className="needle" />
        </svg>
        <div className="gauge-score">{v.risk_score === null ? "—" : formatScore(score)}<small> / 100</small></div>
        <div className="verdict rise" style={delay(1.6)}>
          <ActionBadge action={v.recommended_action} />
          <span className="muted">{humanize(v.confidence)} confidence</span>
        </div>
        {v.sar_recommendation?.recommended && (
          <p className="small muted rise" style={delay(1.9)}>Suspicious transaction report recommended, for a human to decide.</p>
        )}
      </div>
      <ul className="signals">
        {v.signals.map((s, i) => (
          <li key={s.signal} className={`rise ${s.available ? "" : "unavailable"}`} style={delay(i * 0.16)} title={s.rationale}>
            <span>{humanize(s.signal)}<small>weight {Math.round(s.weight * 100)}%</small></span>
            <span className="bar">
              {s.available && <i style={{ width: `${(s.value ?? 0) * 100}%`, ...delay(0.2 + i * 0.16) }} />}
            </span>
            <b>{s.available && s.value !== null ? s.value.toFixed(2) : "n/a"}</b>
          </li>
        ))}
      </ul>
    </div>
  );
}

// 5 ─ Explain and verify
const CHECKS = ["Structure", "Evidence integrity", "Citations", "Decision", "Regulatory", "Language", "Label leakage"];
const CHECK_NAMES: Record<string, string> = {
  STRUCTURE: "Complete structure", BUNDLE_INTEGRITY: "Evidence untampered", CITATION_GROUNDING: "Every figure is cited",
  DECISION_CONSISTENCY: "Matches the decision", REGULATORY: "Only approved regulations", LANGUAGE: "No accusatory wording",
  LABEL_LEAKAGE: "No answer-key leakage",
};

export function ExplainScene({ draft, check }: {
  draft?: Step<DraftView>; check?: Step<CheckView>;
}) {
  if (draft?.state === "error") return <Failed step={draft} />;
  const v = check?.view;
  const replaced = !!v?.sections;
  const sections = v?.sections ?? draft?.view?.sections;
  const writer = replaced ? v?.presented_generator : draft?.view?.generator;
  return (
    <div className="scene explain">
      <div className="paper">
        <div className="paper-head">
          <span>Investigation report</span>
          <small>{!sections ? "Writing…" : `${writer === "LLM" ? "Written by AI" : "Written from the evidence template"} · excerpt`}</small>
          {v && <b className={`stamp ${v.status === "VALIDATED" ? "stamp-ok" : "stamp-bad"}`}>{v.status === "VALIDATED" ? "Validated" : "Needs review"}</b>}
        </div>
        {sections ? <Typed key={replaced ? "final" : "draft"} sections={sections} /> : <Lines />}
      </div>
      <div className="checks">
        <h4>Output Validator</h4>
        {check?.state === "error" && <Failed step={check} />}
        {draft?.view?.status === "FALLBACK_TEMPLATE" && (
          <p className="note note-info small">
            Template report: {fallbackNote(draft.view.fallback_reason, 0)}. It is checked in the same way.
          </p>
        )}
        {v?.rejected.map((r) => (
          <div key={r.reason} className="note note-warn small rise">
            <strong>AI draft rejected.</strong> {r.issues[0] ?? r.reason}. A checked template report replaced it.
          </div>
        ))}
        <ul>
          {v
            ? v.checks.map((c, i) => (
                <li key={c.check} className={`check-row pop ${c.passed ? "passed" : "failed"}`} style={delay(i * 0.24)} title={c.description}>
                  <i><Icon name={c.passed ? "check" : "cross"} size={14} /></i>{CHECK_NAMES[c.check] ?? humanize(c.check)}
                </li>
              ))
            : CHECKS.map((name) => <li key={name} className={`check-row pending ${check ? "busy" : ""}`}><i />{name}</li>)}
        </ul>
      </div>
    </div>
  );
}

function Typed({ sections }: { sections: DraftSection[] }) {
  const excerpt = useMemo(() => sections.map((s) => ({ title: s.title, lines: s.statements.slice(0, 2) })), [sections]);
  const total = useMemo(() => excerpt.reduce((n, s) => n + s.lines.reduce((m, l) => m + l.text.length, 0), 0), [excerpt]);
  const [chars, setChars] = useState(0);
  useEffect(() => {
    if (prefersReducedMotion()) {
      setChars(total);
      return;
    }
    const start = performance.now();
    const timer = window.setInterval(() => {
      const n = Math.round(total * Math.min(1, (performance.now() - start) / 2400));
      setChars(n);
      if (n >= total) window.clearInterval(timer);
    }, 30);
    return () => window.clearInterval(timer);
  }, [total]);

  let used = 0;
  return (
    <div className="typed">
      {excerpt.map((s) => {
        if (used > chars) return null;
        const body = s.lines.map((l, i) => {
          const take = chars - used;
          used += l.text.length;
          if (take <= 0) return null;
          return (
            <p key={i}>
              {l.text.slice(0, take)}
              {take < l.text.length ? <i className="caret" /> : <sup>{l.fact_ids.slice(0, 3).join(" ")}</sup>}
            </p>
          );
        });
        return <div key={s.title}><h5>{s.title.replace(/^\d+\.\s*/, "")}</h5>{body}</div>;
      })}
    </div>
  );
}

function Lines() {
  return <div className="lines">{[92, 80, 97, 64, 88, 73, 94, 58].map((w, i) => <i key={i} style={{ width: `${w}%`, ...delay(i * 0.12) }} />)}</div>;
}

export function Working({ label }: { label: string }) {
  return (
    <div className="working" role="status">
      <span className="radar"><i /><i /><i /></span>
      <p>{label}…</p>
    </div>
  );
}
