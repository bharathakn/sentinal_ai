import { afterEach, describe, expect, it, vi } from "vitest";
import { escapeHtml } from "../components/NetworkGraph";
import { ApiError, api, setUnauthorizedHandler } from "./api";
import { actionTone, bandsFrom, formatAmount, humanize, statusLabel } from "./format";
import { parseHash } from "./router";

vi.mock("react-force-graph-2d", () => ({ default: () => null }));

function mockFetch(status: number, body: unknown, headers: Record<string, string> = {}) {
  const fn = vi.fn(async () => new Response(body === undefined ? null : JSON.stringify(body), { status, headers }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
  setUnauthorizedHandler(() => {});
});

describe("format", () => {
  it("formats amounts in Indian grouping and keeps unparseable values", () => {
    expect(formatAmount("1050368.45", "INR")).toBe("INR 10,50,368.45");
    expect(formatAmount(null)).toBe("—");
    expect(formatAmount("n/a")).toBe("n/a");
  });

  it("maps actions to tones and codes to labels", () => {
    expect(actionTone("BLOCK")).toBe("critical");
    expect(actionTone("CLEAR")).toBe("ok");
    expect(actionTone(undefined)).toBe("neutral");
    expect(humanize("HUMAN_REVIEW")).toBe("Human review");
    expect(statusLabel("AWAITING_REVIEW")).toBe("Awaiting review");
  });

  it("builds score bands only from the case's own thresholds", () => {
    expect(bandsFrom(null)).toBeNull();
    const b = bandsFrom({ monitor_threshold: 30, escalate_threshold: 55, block_threshold: 80 })!;
    expect(b.map((x) => [x.from, x.to])).toEqual([[0, 30], [30, 55], [55, 80], [80, 100]]);
  });
});

describe("router", () => {
  it("parses queue and case routes", () => {
    expect(parseHash("")).toEqual({ name: "home" });
    expect(parseHash("#/cases")).toEqual({ name: "queue" });
    expect(parseHash("#/runs/RUN-AB12")).toEqual({ name: "run", runId: "RUN-AB12" });
    expect(parseHash("#/cases/CASE-ABC123")).toEqual({ name: "case", caseId: "CASE-ABC123", tab: undefined });
    expect(parseHash("#/cases/CASE-1/network")).toEqual({ name: "case", caseId: "CASE-1", tab: "network" });
    expect(parseHash("#/cases/../../x")).toEqual({ name: "home" });
  });
});

describe("escapeHtml", () => {
  it("neutralises markup in graph tooltips", () => {
    expect(escapeHtml(`<img src=x onerror="a()">&'`)).toBe("&lt;img src=x onerror=&quot;a()&quot;&gt;&amp;&#39;");
  });
});

describe("api client", () => {
  it("sends same-origin credentials to relative URLs", async () => {
    const f = mockFetch(200, { total: 0, limit: 50, offset: 0, items: [], prototype_notice: "" });
    await api.listCases({ status: "AWAITING_REVIEW", action: "" });
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/cases?status=AWAITING_REVIEW");
    expect(init.credentials).toBe("same-origin");
  });

  it("calls the unauthorized handler on 401, except for sign-in", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockFetch(401, { detail: "Session expired. Please sign in again." });
    await expect(api.getCase("CASE-1")).rejects.toMatchObject({ status: 401 });
    expect(handler).toHaveBeenCalledTimes(1);
    mockFetch(401, { detail: "Incorrect username or password." });
    await expect(api.login("a", "b", true)).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("surfaces validation messages and Retry-After", async () => {
    mockFetch(422, { detail: [{ msg: "Field required" }] });
    await expect(api.decide("C", "CLEAR", "")).rejects.toMatchObject({ message: "Field required" });
    mockFetch(429, { detail: "locked" }, { "Retry-After": "120" });
    await expect(api.login("a", "b", true)).rejects.toMatchObject({ status: 429, retryAfter: 120 });
  });

  it("sends only the action and rationale with a decision", async () => {
    const f = mockFetch(200, {});
    await api.decide("CASE-1", "ESCALATE", "Layering chain");
    const init = (f.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(JSON.parse(String(init.body))).toEqual({ action: "ESCALATE", rationale: "Layering chain" });
  });
});
