import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { AuditView, PipelineView } from "../components/AuditView";
import { DecisionPanel } from "../components/DecisionPanel";
import { EvidenceView } from "../components/EvidenceView";
import { ReportView } from "../components/ReportView";
import { RiskPanel } from "../components/RiskPanel";
import { Badge, ErrorNote, KeyValue, Panel, Spinner } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { formatAmount, formatDateTime, statusLabel } from "../lib/format";
import { navigate } from "../lib/router";
import type { CaseRecord, NetworkView } from "../lib/types";

// The graph library is large and canvas-based: load it only when the tab opens.
const NetworkGraph = lazy(() => import("../components/NetworkGraph").then((m) => ({ default: m.NetworkGraph })));

const TABS = [
  { key: "report", label: "Report" },
  { key: "evidence", label: "Evidence" },
  { key: "network", label: "Network" },
  { key: "audit", label: "Audit trail" },
  { key: "pipeline", label: "Pipeline" },
] as const;

export function CasePage({ caseId, tab = "report" }: { caseId: string; tab?: string }) {
  const [record, setRecord] = useState<CaseRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setRecord(await api.getCase(caseId));
      setError(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return;
      setError(e instanceof ApiError && e.status === 404 ? `Case ${caseId} was not found.` : "Could not load the case.");
    }
  }, [caseId]);

  useEffect(() => { setRecord(null); load(); }, [load]);
  // Poll while the investigation is still running.
  useEffect(() => {
    if (!record || !(record.status === "RECEIVED" || record.status === "INVESTIGATING")) return;
    const t = window.setTimeout(load, 3000);
    return () => window.clearTimeout(t);
  }, [record, load]);

  if (error) return <div className="page"><BackLink /><ErrorNote>{error}</ErrorNote></div>;
  if (!record) return <div className="page"><BackLink /><Spinner label="Loading case…" /></div>;

  const tx = record.transaction;
  const inv = record.investigation;
  const running = record.status === "RECEIVED" || record.status === "INVESTIGATING";
  const current = TABS.some((t) => t.key === tab) ? tab : "report";

  return (
    <div className="page">
      <BackLink />
      <div className="case-head">
        <div>
          <h1 className="mono">{record.case_id}</h1>
          <div className="case-sub">
            <span className={`status status-${record.status.toLowerCase()}`}>{statusLabel(record.status)}</span>
            <span><strong>{formatAmount(tx.amount, tx.currency)}</strong> via {tx.channel}</span>
            <span className="mono">{tx.sender.account_id ?? "?"} → {tx.receiver.account_id ?? "?"}</span>
            <span className="muted">{formatDateTime(tx.timestamp)}</span>
          </div>
        </div>
        <Badge tone="warn" title={record.prototype_notice}>Synthetic data</Badge>
      </div>

      {running && <Panel><Spinner label="Investigation in progress — Agents 1–5 and the Output Validator are running…" /></Panel>}
      {record.status === "INVESTIGATION_FAILED" && (
        <ErrorNote>The investigation failed ({record.investigation_error}). Submit the alert again to retry.</ErrorNote>
      )}

      {inv && (
        <div className="case-grid">
          <div className="case-main">
            <div className="tabs" role="tablist">
              {TABS.map((t) => (
                <button key={t.key} role="tab" aria-selected={current === t.key}
                        className={`tab ${current === t.key ? "tab-active" : ""}`}
                        onClick={() => navigate(`/cases/${record.case_id}/${t.key}`)}>{t.label}</button>
              ))}
            </div>
            <Panel>
              {current === "report" && (inv.agent5_output
                ? <ReportView caseId={record.case_id} report={inv.agent5_output} validation={inv.validation_output}
                              rejectedCount={inv.rejected_reports?.length ?? 0}
                              regulatory={inv.agent4_output?.regulatory_matches ?? []} />
                : <p className="note note-warn">No report was generated. {inv.halt_reason ?? ""}</p>)}
              {current === "evidence" && <EvidenceView inv={inv} />}
              {current === "network" && <NetworkTab caseId={record.case_id} />}
              {current === "audit" && <AuditView events={record.audit_trail} />}
              {current === "pipeline" && <PipelineView trace={inv.pipeline_trace ?? []} status={inv.pipeline_status} halt={inv.halt_reason} />}
            </Panel>
          </div>
          <div className="case-side">
            <DecisionPanel record={record} onDecided={setRecord} />
            <RiskPanel a4={inv.agent4_output} summary={record.summary} />
            <Panel title="Alert">
              <KeyValue items={[
                ["Transaction", <span className="mono">{tx.raw_record_id}</span>],
                ["Source", `${record.alert.source === "SYNTHETIC_FEED" ? "Synthetic monitoring feed" : "API"}${record.alert.source_system ? ` (${record.alert.source_system})` : ""}`],
                ["Alert id", record.alert.alert_id ?? "—"],
                ["Received", formatDateTime(record.alert.received_at_utc)],
                ["Anomaly model", inv.agent1_output?.combined_confidence != null
                  ? `combined confidence ${inv.agent1_output.combined_confidence.toFixed(3)} (heuristic, not a probability)` : "—"],
              ]} />
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}

function BackLink() {
  return <button className="btn btn-ghost back" onClick={() => navigate("/")}>← Case queue</button>;
}

function NetworkTab({ caseId }: { caseId: string }) {
  const [view, setView] = useState<NetworkView | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.getNetwork(caseId).then(setView).catch((e) => setError(e instanceof Error ? e.message : "Failed to load network"));
  }, [caseId]);
  if (error) return <ErrorNote>{error}</ErrorNote>;
  if (!view) return <Spinner label="Loading network…" />;
  return <Suspense fallback={<Spinner label="Loading graph…" />}><NetworkGraph view={view} /></Suspense>;
}
