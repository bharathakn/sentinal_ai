import { useMemo, useState } from "react";
import { formatDateTime, humanize } from "../lib/format";
import type { Fact, Investigation, ProviderResult } from "../lib/types";
import { Badge } from "./ui";

const SECTION_ORDER = ["CASE_SUMMARY", "ANOMALY_FINDINGS", "EVIDENCE_SUMMARY", "NETWORK_ANALYSIS",
  "REGULATORY_ASSESSMENT", "RECOMMENDED_ACTION"];

function providers(a2: Investigation["agent2_output"]): [string, ProviderResult][] {
  if (!a2) return [];
  return Object.entries(a2).filter(([, v]) => v && typeof v === "object" && !Array.isArray(v)
    && "source" in (v as object) && "status" in (v as object)) as [string, ProviderResult][];
}

// Retrieval outcome only: FOUND / NO_MATCH are successful lookups; MATCH_FOUND (sanctions) needs attention.
function statusTone(status: string) {
  if (status === "MATCH_FOUND") return "critical" as const;
  if (["FOUND", "NO_MATCH", "NO_ARTICLES"].includes(status)) return "ok" as const;
  if (status === "NOT_FOUND") return "neutral" as const;
  return "warn" as const; // VALIDATION_ERROR, PROVIDER_ERROR, AUTH_ERROR, TIMEOUT …
}

export function EvidenceView({ inv }: { inv: Investigation }) {
  const facts = inv.agent5_output?.evidence_bundle?.facts ?? [];
  const [q, setQ] = useState("");
  const grouped = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const m = new Map<string, Fact[]>();
    for (const f of facts) {
      if (needle && !`${f.fact_id} ${f.label} ${f.value} ${f.source}`.toLowerCase().includes(needle)) continue;
      m.set(f.section, [...(m.get(f.section) ?? []), f]);
    }
    return SECTION_ORDER.filter((s) => m.has(s)).map((s) => [s, m.get(s)!] as const);
  }, [facts, q]);
  const provs = providers(inv.agent2_output);

  return (
    <div className="evidence">
      <h3>Evidence sources (Agent 2)</h3>
      <div className="table-wrap">
        <table className="table compact">
          <thead><tr><th>Provider</th><th>Source</th><th>Mode</th><th>Status</th><th>Entity</th><th>Retrieved</th></tr></thead>
          <tbody>
            {provs.map(([k, p]) => (
              <tr key={k}>
                <td>{humanize(k)}</td>
                <td className="small">{p.source}</td>
                <td><Badge tone={p.source_mode === "LIVE" ? "neutral" : "warn"}>{p.source_mode}</Badge></td>
                <td><Badge tone={statusTone(p.status)}>{humanize(p.status)}</Badge></td>
                <td className="mono small">{p.requested_entity_id ?? "—"}</td>
                <td className="small muted">{formatDateTime(p.retrieved_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(inv.agent2_output?.warnings?.length ?? 0) > 0 && (
        <ul className="small muted">{inv.agent2_output!.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
      )}
      <div className="row space">
        <h3>Evidence facts ({facts.length})</h3>
        <input className="search" placeholder="Filter facts…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter facts" />
      </div>
      <p className="small muted">Every fact the report may cite, with the agent and source that produced it.</p>
      {grouped.map(([section, list]) => (
        <details key={section} open={section !== "CASE_SUMMARY"} className="fact-group">
          <summary>{humanize(section)} ({list.length})</summary>
          <div className="table-wrap">
            <table className="table compact">
              <thead><tr><th>Id</th><th>Fact</th><th>Value</th><th>Source</th></tr></thead>
              <tbody>
                {list.map((f) => (
                  <tr key={f.fact_id}>
                    <td className="mono">{f.fact_id}</td>
                    <td>{f.label}</td>
                    <td className="value-cell">{f.value}</td>
                    <td className="small">{f.source}{f.source_mode ? ` (${f.source_mode})` : ""}<div className="muted">{humanize(f.source_agent)}</div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ))}
    </div>
  );
}
