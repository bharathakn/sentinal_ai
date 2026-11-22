// API client. All calls go to relative /api URLs (first-party cookie).
import type { DemoInfo, Run, RunEventPage } from "./run";
import type { AnalystAction, AuditEvent, CaseList, CaseRecord, NetworkView, User } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string, public retryAfter?: number) {
    super(message);
  }
}

type UnauthorizedHandler = () => void;
let onUnauthorized: UnauthorizedHandler = () => {};
export function setUnauthorizedHandler(fn: UnauthorizedHandler) {
  onUnauthorized = fn;
}

function detailOf(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length && typeof d[0] === "object" && d[0] && "msg" in d[0]) {
      return String((d[0] as { msg: unknown }).msg);
    }
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}, opts: { authRedirect?: boolean } = {}): Promise<T> {
  const res = await fetch(path, {
    credentials: "same-origin",
    ...init,
    headers: { Accept: "application/json", ...(init.body ? { "Content-Type": "application/json" } : {}), ...init.headers },
  });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!res.ok) {
    if (res.status === 401 && opts.authRedirect !== false) onUnauthorized();
    const retry = Number(res.headers.get("Retry-After")) || undefined;
    throw new ApiError(res.status, detailOf(body, `Request failed (${res.status})`), retry);
  }
  return body as T;
}

export const api = {
  login: (username: string, password: string, remember: boolean) =>
    request<User>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ username, password, remember }) },
      { authRedirect: false }),
  signup: (username: string, display_name: string, password: string, remember: boolean) =>
    request<User>("/api/v1/auth/signup", { method: "POST", body: JSON.stringify({ username, display_name, password, remember }) },
      { authRedirect: false }),
  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }, { authRedirect: false }),
  me: () => request<User>("/api/v1/auth/me", {}, { authRedirect: false }),
  changePassword: (current_password: string, new_password: string) =>
    request<void>("/api/v1/auth/password", { method: "POST", body: JSON.stringify({ current_password, new_password }) }),
  listCases: (params: { status?: string; action?: string; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== "" && q.set(k, String(v)));
    return request<CaseList>(`/api/v1/cases${q.toString() ? `?${q}` : ""}`);
  },
  getCase: (id: string) => request<CaseRecord>(`/api/v1/cases/${encodeURIComponent(id)}`),
  getNetwork: (id: string) => request<NetworkView>(`/api/v1/cases/${encodeURIComponent(id)}/network`),
  getAudit: (id: string) => request<AuditEvent[]>(`/api/v1/cases/${encodeURIComponent(id)}/audit`),
  decide: (id: string, action: AnalystAction, rationale: string) =>
    request<CaseRecord>(`/api/v1/cases/${encodeURIComponent(id)}/decision`, {
      method: "POST",
      body: JSON.stringify({ action, rationale }),
    }),
  submitAlert: (transaction_id: string) =>
    request<{ case_id: string; status: string; duplicate: boolean }>("/api/v1/alerts", {
      method: "POST",
      body: JSON.stringify({ transaction_id, source_system: "dashboard" }),
    }),
  health: () => request<{ report_writer?: string; signup_open?: boolean }>("/health", {}, { authRedirect: false }),
  demoInfo: () => request<DemoInfo>("/api/v1/datasets/demo"),
  sampleCsvUrl: "/api/v1/datasets/sample.csv",
  startDemoRun: (top: number, llm: boolean) =>
    request<Run>(`/api/v1/runs/demo?${new URLSearchParams({ investigate_top: String(top), llm_reports: String(llm) })}`, {
      method: "POST",
    }),
  startUploadRun: (file: File, top: number, llm: boolean) =>
    request<Run>(`/api/v1/runs/upload?${new URLSearchParams({ filename: file.name, investigate_top: String(top), llm_reports: String(llm) })}`, {
      method: "POST",
      body: file,
      headers: { "Content-Type": file.name.toLowerCase().endsWith(".json") ? "application/json" : "text/csv" },
    }),
  listRuns: () => request<{ items: Run[] }>("/api/v1/runs?limit=5"),
  getRun: (id: string) => request<Run>(`/api/v1/runs/${encodeURIComponent(id)}`),
  getRunEvents: (id: string, after: number) =>
    request<RunEventPage>(`/api/v1/runs/${encodeURIComponent(id)}/events?after=${after}`),
  reportMarkdownUrl: (id: string) => `/api/v1/cases/${encodeURIComponent(id)}/report?format=markdown`,
};
