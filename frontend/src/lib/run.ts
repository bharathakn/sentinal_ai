// A dataset run is an append-only log of real agent events. The live view is a pure
// function of "the events shown so far"; the player only paces when each one is shown.
import type { CaseSummary, NetworkView } from "./types";

export interface DatasetInfo {
  kind: "DEMO" | "UPLOAD";
  name: string;
  rows: number;
  rejected_rows: number;
  row_errors: string[];
  ignored_columns: string[];
}

export interface DemoInfo {
  name: string;
  rows: number;
  accounts: number;
  first_date: string;
  last_date: string;
  channels: string[];
  total_amount_inr: number;
}

export interface ScreenedTx {
  transaction_id: string;
  amount: string;
  currency: string;
  channel: string;
  sender: string;
  receiver: string;
  combined_confidence: number;
  flagged: boolean;
  /** Demo only: the suspected pattern this transaction was picked as an example of. */
  lead?: string | null;
}

export interface RunResult {
  screened: number;
  flagged: number;
  investigated: number;
  not_investigated: number;
  by_action: Record<string, number>;
  validated: number;
  sar_recommended: number;
  failed: number;
}

export interface Run {
  run_id: string;
  status: "QUEUED" | "SCREENING" | "INVESTIGATING" | "COMPLETED" | "FAILED";
  created_by: string;
  created_at_utc: string;
  dataset: DatasetInfo;
  settings: { investigate_top: number; llm_reports: boolean };
  result: RunResult | null;
  error: string | null;
}

export interface RunEvent {
  seq: number;
  at_utc: string;
  type: string;
  case_id: string | null;
  // The payload depends on `type`; see src/api/runs.py and src/api/run_events.py.
  data: any;
}

export interface RunEventPage {
  status: Run["status"];
  events: RunEvent[];
  next: number;
  more: boolean;
}

export type NodeId =
  | "anomaly_detector" | "evidence_gatherer" | "network_analyser"
  | "risk_assessor" | "explanation_generator" | "output_validator";

export interface AnomalyView {
  status: string;
  combined_confidence: number | null;
  warnings: string[];
  xgboost: { fraud_probability: number | null; threshold_used: number | null };
  isolation_forest: { anomaly_score: number | null; threshold_used: number | null };
  drivers: { feature: string; shap_value: number; feature_value: number | null }[];
}

export interface EvidenceProviders {
  status: string;
  providers: { name: string; source: string | null; source_mode: string | null; status: string; error?: string | null }[];
}

export interface RiskView {
  status: string;
  risk_score: number | null;
  score_band_action: string | null;
  recommended_action: string;
  confidence: string;
  evidence_coverage: number | null;
  overrides_applied: { rule_id: string; description: string; minimum_action: string }[];
  sar_recommendation: { recommended: boolean } | null;
  thresholds: { monitor_threshold: number; escalate_threshold: number; block_threshold: number };
  signals: { signal: string; weight: number; value: number | null; available: boolean; rationale: string }[];
}

export interface DraftSection {
  title: string;
  statements: { text: string; fact_ids: string[]; origin: string }[];
}

export interface DraftView {
  status: string;
  generator: string | null;
  fallback_reason: string | null;
  sections: DraftSection[];
}

export interface CheckView {
  status: string;
  checks_passed: number;
  checks_total: number;
  checks: { check: string; description: string; passed: boolean; issues: string[] }[];
  rejected: { reason: string; issues: string[] }[];
  presented_generator: string | null;
  sections: DraftSection[] | null;
}

export interface NodeViews {
  anomaly_detector: AnomalyView;
  evidence_gatherer: EvidenceProviders;
  network_analyser: NetworkView;
  risk_assessor: RiskView;
  explanation_generator: DraftView;
  output_validator: CheckView;
}

export interface Step<T> {
  state: "running" | "done" | "error";
  ms?: number;
  error?: string | null;
  view?: T;
}

export interface LiveCase {
  id: string;
  rank: number;
  tx: ScreenedTx;
  timestamp: string | null;
  steps: { [K in NodeId]?: Step<NodeViews[K]> };
  done: boolean;
  status?: string;
  summary?: CaseSummary;
}

export interface Screening {
  total: number;
  screened: number;
  flagged: number;
  histogram: number[];
  flaggedHistogram: number[];
  stream: ScreenedTx[];
  selected: ScreenedTx[];
  /** True when the demo picked different suspected patterns rather than the top scores. */
  varied: boolean;
  done: boolean;
}

export interface LiveRun {
  phase: "waiting" | "screening" | "investigating" | "complete" | "failed";
  dataset: DatasetInfo | null;
  screening: Screening;
  cases: LiveCase[];
  result: RunResult | null;
  error: string | null;
}

export const STAGES: { name: string; agent: string; verb: string; blurb: string; nodes: NodeId[] }[] = [
  { name: "Detect", agent: "Anomaly Detector", verb: "Detecting what is abnormal",
    blurb: "Two ML models score every transaction", nodes: ["anomaly_detector"] },
  { name: "Gather", agent: "Evidence Gatherer", verb: "Gathering the evidence",
    blurb: "Bank, KYC, device and sanctions checks", nodes: ["evidence_gatherer"] },
  { name: "Trace", agent: "Network Analyser", verb: "Following the money",
    blurb: "Layering, mules and circular flows", nodes: ["network_analyser"] },
  { name: "Assess", agent: "Risk Assessor", verb: "Weighing the risk",
    blurb: "Seven signals, one explainable score", nodes: ["risk_assessor"] },
  { name: "Explain", agent: "Explanation Generator", verb: "Writing and checking the report",
    blurb: "A cited report, checked before you see it", nodes: ["explanation_generator", "output_validator"] },
];

export function deriveRun(events: RunEvent[]): LiveRun {
  const s: Screening = {
    total: 0, screened: 0, flagged: 0, histogram: [], flaggedHistogram: [], stream: [], selected: [], varied: false, done: false,
  };
  const run: LiveRun = { phase: "waiting", dataset: null, screening: s, cases: [], result: null, error: null };
  const byId = new Map<string, LiveCase>();
  for (const { type, data: d, case_id } of events) {
    const c = case_id ? byId.get(case_id) : undefined;
    if (type === "run.queued" || type === "run.started") run.dataset = d.dataset;
    else if (type === "screening.started") {
      run.phase = "screening";
      s.total = d.total;
    } else if (type === "screening.progress") {
      s.screened = d.screened;
      s.flagged = d.flagged;
      s.histogram = d.histogram;
      s.flaggedHistogram = d.flagged_histogram;
      s.stream = [...[...d.sample].reverse(), ...s.stream].slice(0, 12);
    } else if (type === "screening.completed") {
      s.done = true;
      s.selected = d.selected;
      s.varied = d.selection_rule === "varied";
      s.flagged = d.flagged;
    } else if (type === "case.started" && case_id) {
      run.phase = "investigating";
      const live: LiveCase = { id: case_id, rank: d.rank, tx: d.transaction, timestamp: d.timestamp, steps: {}, done: false };
      byId.set(case_id, live);
      run.cases.push(live);
    } else if (type === "agent.started" && c) {
      c.steps[d.node as NodeId] = { state: "running" };
    } else if (type === "agent.completed" && c) {
      const ok = d.outcome === "OK" && Object.keys(d.view ?? {}).length > 0;
      c.steps[d.node as NodeId] = { state: ok ? "done" : "error", ms: d.duration_ms, error: d.error, view: ok ? d.view : undefined };
    } else if (type === "case.completed" && c) {
      c.done = true;
      c.status = d.status;
      c.summary = d.summary;
    } else if (type === "run.completed") {
      run.phase = "complete";
      run.result = d.result;
    } else if (type === "run.failed") {
      run.phase = "failed";
      run.error = d.error;
    }
  }
  return run;
}

export type StageState = "idle" | "running" | "done" | "error" | "skipped";

export function stageState(c: LiveCase | undefined, index: number): StageState {
  if (!c) return "idle";
  const steps = STAGES[index].nodes.map((n) => c.steps[n]);
  if (steps.some((s) => s?.state === "error")) return "error";
  if (steps.every((s) => s?.state === "done")) return "done";
  if (steps.some(Boolean)) return c.done ? "error" : "running";
  return c.done ? "skipped" : "idle";
}

/** The stage being worked on: the latest one with any event. */
export function currentStage(c: LiveCase): number {
  for (let i = STAGES.length - 1; i >= 0; i--) if (STAGES[i].nodes.some((n) => c.steps[n])) return i;
  return 0;
}

// [first case, each later case], in ms. Five cases come to about 40 seconds in all.
const HOLD_MS: Record<string, [number, number]> = {
  anomaly_detector: [1600, 520], evidence_gatherer: [1800, 520], network_analyser: [2800, 1000],
  risk_assessor: [2200, 750], explanation_generator: [2200, 560], output_validator: [1900, 650],
};

/** How long `previous` stays on screen before the next event is shown. */
export function holdAfter(previous: RunEvent | undefined, caseRank: number, caseCount = 5): number {
  if (!previous) return 0;
  const { type, data } = previous;
  if (type === "screening.started") return 300;
  if (type === "screening.progress") return 150;
  if (type === "screening.completed") return 2200;
  if (type.startsWith("run.")) return 100;
  const later = caseRank > 1 ? 1 : 0;
  // With more cases each later one is quicker, so ten cases do not take twice as long.
  const squeeze = later && caseCount > 5 ? Math.max(0.45, 4 / (caseCount - 1)) : 1;
  if (type === "case.started") return (later ? 300 : 500) * squeeze;
  if (type === "case.completed") return (later ? 400 : 500) * squeeze;
  if (type === "agent.started") return (later ? 50 : 250) * squeeze;
  if (type === "agent.completed") return (HOLD_MS[data.node as string]?.[later] ?? 600) * squeeze;
  return 100;
}
