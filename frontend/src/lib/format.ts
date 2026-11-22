// Display helpers. Values are shown as the API supplies them; nothing is recomputed.

export function formatAmount(amount: string | number | null | undefined, currency?: string | null): string {
  if (amount === null || amount === undefined || amount === "") return "—";
  const n = typeof amount === "number" ? amount : Number(amount);
  if (!Number.isFinite(n)) return String(amount);
  const formatted = n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return currency ? `${currency} ${formatted}` : formatted;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-GB", {
    year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", timeZoneName: "short",
  });
}

export function relativeTime(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "—";
  const s = Math.round((now.getTime() - new Date(iso).getTime()) / 1000);
  if (!Number.isFinite(s)) return "—";
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export function formatScore(score: number | null | undefined): string {
  return score === null || score === undefined ? "—" : score.toFixed(2);
}

export function humanize(code: string | null | undefined): string {
  if (!code) return "—";
  return code.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
}

export type Tone = "critical" | "high" | "medium" | "low" | "ok" | "neutral" | "warn";

export function actionTone(action: string | null | undefined): Tone {
  switch (action) {
    case "BLOCK": return "critical";
    case "ESCALATE": return "high";
    case "HUMAN_REVIEW": return "medium";
    case "MONITOR": return "low";
    case "CLEAR": return "ok";
    default: return "neutral";
  }
}

export function validationTone(status: string | null | undefined): Tone {
  if (status === "VALIDATED") return "ok";
  if (status === "NEEDS_HUMAN_REVIEW" || status === "NOT_VALIDATED") return "warn";
  return "neutral";
}

export function statusLabel(status: string): string {
  return {
    RECEIVED: "Queued",
    INVESTIGATING: "Investigating",
    AWAITING_REVIEW: "Awaiting review",
    INVESTIGATION_FAILED: "Investigation failed",
    DECIDED: "Decided",
  }[status] ?? humanize(status);
}

/** Why the template writer was used. Only a rejected draft is a validation failure. */
export function fallbackNote(reason: string | null | undefined, rejected: number): string {
  if (rejected > 0) return "the AI draft failed validation and was replaced";
  if (reason?.includes("429")) return "the AI writer hit Groq's rate limit";
  return "the AI writer did not return a usable report";
}

export interface Thresholds {
  monitor_threshold: number;
  escalate_threshold: number;
  block_threshold: number;
}

/** Score bands from the case's own Agent 4 configuration snapshot (never hard-coded). */
export function bandsFrom(t: Thresholds | null | undefined) {
  if (!t) return null;
  return [
    { from: 0, to: t.monitor_threshold, label: "Clear", tone: "ok" as Tone },
    { from: t.monitor_threshold, to: t.escalate_threshold, label: "Monitor", tone: "low" as Tone },
    { from: t.escalate_threshold, to: t.block_threshold, label: "Escalate", tone: "high" as Tone },
    { from: t.block_threshold, to: 100, label: "Block", tone: "critical" as Tone },
  ];
}
