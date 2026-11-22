import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LoginPage } from "../pages/LoginPage";
import type { CaseRecord, Report } from "../lib/types";
import { DecisionPanel } from "./DecisionPanel";
import { ReportView } from "./ReportView";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stubFetch(status: number, body: unknown, headers: Record<string, string> = {}) {
  const fn = vi.fn(async () => new Response(JSON.stringify(body), { status, headers }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("LoginPage", () => {
  function fill(user = "alice", pw = "secret-password") {
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: user } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: pw } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  }

  it("signs in and keeps the analyst signed in by default", async () => {
    const f = stubFetch(200, { username: "alice", display_name: "Alice" });
    const onSignedIn = vi.fn();
    render(<LoginPage onSignedIn={onSignedIn} />);
    expect((screen.getByLabelText(/Keep me signed in/) as HTMLInputElement).checked).toBe(true);
    fill();
    await waitFor(() => expect(onSignedIn).toHaveBeenCalledWith({ username: "alice", display_name: "Alice" }));
    const body = JSON.parse(String((f.mock.calls[0] as unknown as [string, RequestInit])[1].body));
    expect(body).toEqual({ username: "alice", password: "secret-password", remember: true });
  });

  it("shows a generic error and clears the password on failure", async () => {
    stubFetch(401, { detail: "Incorrect username or password." });
    render(<LoginPage onSignedIn={vi.fn()} />);
    fill();
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Incorrect username or password.");
    expect((screen.getByLabelText("Password") as HTMLInputElement).value).toBe("");
  });

  it("explains a lockout", async () => {
    stubFetch(429, { detail: "Too many" }, { "Retry-After": "600" });
    render(<LoginPage onSignedIn={vi.fn()} />);
    fill();
    expect((await screen.findByRole("alert")).textContent).toContain("10 minutes");
  });
});

const report: Report = {
  agent5_run_id: "r1", status: "COMPLETE", generator: "LLM", llm_model: "m", fallback_reason: null, warnings: [],
  validation_status: "NEEDS_HUMAN_REVIEW", report_note: "DRAFT note",
  sections: [{ section: "CASE_SUMMARY", title: "1. Case Summary", statements: [
    { text: "Account ACC_1 sent INR 10.", fact_ids: ["F-001"], origin: "LLM", added_fact_ids: [] },
  ] }],
  evidence_bundle: { bundle_hash: "h", missing_inputs: [], facts: [{
    fact_id: "F-001", section: "CASE_SUMMARY", label: "Amount", value: "INR 10.00", source_agent: "TRANSACTION",
    source: "INDIA_SYNTHETIC", source_field: "transaction.amount", source_mode: "SYNTHETIC", observed_at: null, reference_id: null,
  }] },
};

describe("ReportView", () => {
  it("opens the cited fact with its source, and warns when not validated", () => {
    render(<ReportView caseId="C" report={report} validation={undefined} rejectedCount={0} regulatory={[]} />);
    expect(screen.getByText(/NOT validated/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "F-001" }));
    const card = screen.getByRole("dialog", { name: "Evidence F-001" });
    expect(card.textContent).toContain("INR 10.00");
    expect(card.textContent).toContain("INDIA_SYNTHETIC");
    expect(card.textContent).toContain("SYNTHETIC");
  });
});

function caseRecord(over: Partial<CaseRecord> = {}): CaseRecord {
  return {
    case_id: "CASE-1", status: "AWAITING_REVIEW", created_at_utc: "2026-11-22T00:00:00Z", updated_at_utc: "2026-11-22T00:00:00Z",
    prototype_notice: "", alert: { alert_id: null, source: "API", source_system: null, received_at_utc: "2026-11-22T00:00:00Z" },
    transaction: { raw_record_id: "T1", source_dataset: "INDIA_SYNTHETIC", amount: "10", currency: "INR", timestamp: null,
      channel: "UPI", sender: { account_id: "A", customer_id: null }, receiver: { account_id: "B" }, metadata: null },
    summary: { risk_score: 60, recommended_action: "ESCALATE", score_band_action: "ESCALATE", confidence: "HIGH",
      sar_recommended: true, report_generator: "TEMPLATE", validation_status: "VALIDATED", pipeline_status: "COMPLETE",
      requires_human_review: false, priority_rank: 4 },
    investigation: null, investigation_error: null, analyst_decision: null, decisions: [], audit_trail: [], ...over,
  };
}

describe("DecisionPanel", () => {
  it("requires an action and a rationale, then records the decision", async () => {
    const decided = caseRecord({ status: "DECIDED" });
    const f = stubFetch(200, decided);
    const onDecided = vi.fn();
    render(<DecisionPanel record={caseRecord()} onDecided={onDecided} />);
    const submit = () => screen.getByRole("button", { name: /Choose an action|Confirm/ }) as HTMLButtonElement;
    expect(submit().disabled).toBe(true);
    fireEvent.click(screen.getByRole("radio", { name: /Escalate/ }));
    expect(submit().disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/Rationale/), { target: { value: "Layering chain via mule accounts" } });
    expect(submit().textContent).toBe("Confirm escalate");
    fireEvent.click(submit());
    await waitFor(() => expect(onDecided).toHaveBeenCalledWith(decided));
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/cases/CASE-1/decision");
    expect(JSON.parse(String(init.body))).toEqual({ action: "ESCALATE", rationale: "Layering chain via mule accounts" });
  });

  it("does not allow a decision before the investigation finishes", () => {
    render(<DecisionPanel record={caseRecord({ status: "INVESTIGATING" })} onDecided={vi.fn()} />);
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.getByText(/once the investigation is complete/)).toBeTruthy();
  });
});
