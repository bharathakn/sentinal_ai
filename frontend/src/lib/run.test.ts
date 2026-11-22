import { describe, expect, it } from "vitest";
import { layoutFlow } from "../components/live/moneyFlowLayout";
import { providerOutcome } from "../components/live/Scenes";
import { fileProblem } from "../pages/HomePage";
import { fallbackNote } from "./format";
import { deriveRun, holdAfter, stageState, type RunEvent } from "./run";
import type { NetworkView } from "./types";

let seq = 0;
const ev = (type: string, data: unknown, case_id: string | null = null): RunEvent =>
  ({ seq: ++seq, at_utc: "2026-11-22T00:00:00Z", type, case_id, data });

const events: RunEvent[] = [
  ev("run.queued", { dataset: { name: "Demo" } }),
  ev("screening.started", { total: 1000 }),
  ev("screening.progress", { screened: 500, flagged: 9, histogram: [1], flagged_histogram: [0], sample: [] }),
  ev("screening.completed", { flagged: 9, selected: [] }),
  ev("case.started", { rank: 1, transaction: { transaction_id: "T1" }, timestamp: null }, "C1"),
  ev("agent.started", { node: "anomaly_detector" }, "C1"),
  ev("agent.completed", { node: "anomaly_detector", outcome: "OK", duration_ms: 5, view: { status: "COMPLETE" } }, "C1"),
  ev("agent.started", { node: "evidence_gatherer" }, "C1"),
];

describe("live run", () => {
  it("shows only what has been played", () => {
    expect(deriveRun(events.slice(0, 1)).phase).toBe("waiting");
    const mid = deriveRun(events.slice(0, 3));
    expect([mid.phase, mid.screening.screened, mid.cases.length]).toEqual(["screening", 500, 0]);
  });

  it("derives each stage's state from real events", () => {
    const c = deriveRun(events).cases[0];
    expect([0, 1, 2].map((i) => stageState(c, i))).toEqual(["done", "running", "idle"]);
  });

  it("marks a failed agent instead of showing it as done", () => {
    const c = deriveRun([...events, ev("agent.completed", { node: "evidence_gatherer", outcome: "ERROR", view: {} }, "C1")]).cases[0];
    expect(stageState(c, 1)).toBe("error");
  });

  it("plays later cases faster than the first", () => {
    const e = ev("agent.completed", { node: "network_analyser" });
    expect(holdAfter(e, 2)).toBeLessThan(holdAfter(e, 1));
  });
});

describe("honest labels", () => {
  it("does not call a rate limit a validation failure", () => {
    expect(fallbackNote("LLM HTTP 429 rate_limit_exceeded", 0)).toContain("rate limit");
    expect(fallbackNote("LLM HTTP 429 rate_limit_exceeded", 0)).not.toContain("validation");
    expect(fallbackNote(null, 1)).toContain("failed validation");
  });

  it("separates not connected from not found", () => {
    expect(providerOutcome("PROVIDER_ERROR", "raised EvidenceSourceNotConnected.")[0]).toBe("Not connected");
    expect(providerOutcome("NOT_FOUND")[0]).toBe("No record");
  });
});

describe("upload checks", () => {
  it("accepts CSV and JSON only", () => {
    expect(fileProblem({ name: "a.CSV", size: 10 })).toBeNull();
    expect(fileProblem({ name: "a.xlsx", size: 10 })).toContain("CSV");
    expect(fileProblem({ name: "a.csv", size: 9 * 1024 * 1024 })).toContain("8 MB");
  });
});

describe("money flow layout", () => {
  it("draws only stored transfers, flowing left to right", () => {
    const edge = (source: string, target: string, investigated = false) =>
      ({ source, target, investigated, patterns: [] });
    const view = { sender_account_id: "S", receiver_account_id: "R", nodes: [],
      edges: [edge("S", "R", true), edge("U", "S"), edge("R", "D")] } as unknown as NetworkView;
    const { nodes, links } = layoutFlow(view);
    const x = (id: string) => nodes.find((n) => n.id === id)!.x;
    expect(x("U")).toBeLessThan(x("S"));
    expect(x("S")).toBeLessThan(x("R"));
    expect(x("R")).toBeLessThan(x("D"));
    expect(links).toHaveLength(3);
  });
});

describe("pacing", () => {
  function total(cases: number): number {
    const nodes = ["anomaly_detector", "evidence_gatherer", "network_analyser", "risk_assessor", "explanation_generator", "output_validator"];
    const log: [RunEvent, number][] = [[ev("run.queued", {}), 0], [ev("screening.started", {}), 0]];
    for (let i = 0; i < 20; i++) log.push([ev("screening.progress", {}), 0]);
    log.push([ev("screening.completed", {}), 0]);
    for (let rank = 1; rank <= cases; rank++) {
      log.push([ev("case.started", {}), rank]);
      for (const node of nodes) log.push([ev("agent.started", { node }), rank], [ev("agent.completed", { node }), rank]);
      log.push([ev("case.completed", {}), rank]);
    }
    return log.reduce((ms, [e, rank]) => ms + holdAfter(e, rank, cases), 0) / 1000;
  }

  it("shows five cases in about 40 seconds, and ten in not much more", () => {
    expect(total(5)).toBeGreaterThan(34);
    expect(total(5)).toBeLessThan(43);
    expect(total(10)).toBeLessThan(48);
  });
});
