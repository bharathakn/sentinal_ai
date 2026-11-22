import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D, { type ForceGraphMethods, type LinkObject, type NodeObject } from "react-force-graph-2d";
import { formatAmount, formatDateTime, humanize } from "../lib/format";
import type { NetworkEdge, NetworkNode, NetworkView } from "../lib/types";
import { Badge } from "./ui";

// Colours read from CSS variables so the graph follows the light/dark theme.
function cssVar(name: string, fallback: string) {
  if (typeof window === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

/** force-graph renders labels as HTML: escape everything that comes from data. */
export function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
}

type GNode = NetworkNode & { x?: number; y?: number };
type GLink = Omit<NetworkEdge, "source" | "target"> & { source: string | GNode; target: string | GNode };

const endId = (e: string | GNode) => (typeof e === "string" ? e : e.id);

export function NetworkGraph({ view }: { view: NetworkView }) {
  const wrap = useRef<HTMLDivElement>(null);
  const fg = useRef<ForceGraphMethods<NodeObject<GNode>, LinkObject<GNode, GLink>> | undefined>(undefined);
  const fitted = useRef(false);
  const [width, setWidth] = useState(800);
  const [selected, setSelected] = useState<string | null>(null);
  const [finding, setFinding] = useState<string | null>(null);

  useEffect(() => {
    const el = wrap.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  // force-graph mutates its data; give it copies.
  const data = useMemo(() => ({
    nodes: view.nodes.map((n) => ({ ...n })) as GNode[],
    links: view.edges.map((e) => ({ ...e })) as GLink[],
  }), [view]);

  const colors = useMemo(() => ({
    sender: cssVar("--c-accent-2", "#2563eb"),
    receiver: cssVar("--c-critical", "#b91c1c"),
    flagged: cssVar("--c-medium", "#a16207"),
    other: cssVar("--c-muted", "#94a3b8"),
    link: cssVar("--c-border-strong", "#94a3b8"),
    linkFlag: cssVar("--c-medium", "#a16207"),
    investigated: cssVar("--c-critical", "#b91c1c"),
    text: cssVar("--c-text", "#0f172a"),
    highlight: cssVar("--c-accent", "#1f4e79"),
  }), []);

  const focusNodes = useMemo(() => {
    if (!finding) return null;
    const f = view.findings.find((x) => x.finding_id === finding);
    return new Set(view.nodes.filter((n) => n.finding_ids.includes(finding)).map((n) => n.id)
      .concat(f ? [f.subject_account_id, ...f.related_account_ids] : []));
  }, [finding, view]);

  const nodeColor = (n: GNode) =>
    n.roles.includes("SENDER") ? colors.sender
      : n.roles.includes("RECEIVER") ? colors.receiver
      : n.patterns.length ? colors.flagged : colors.other;

  const sel = view.nodes.find((n) => n.id === selected) ?? null;
  const selEdges = sel ? view.edges.filter((e) => e.source === sel.id || e.target === sel.id) : [];

  return (
    <div className="network">
      <div className="network-main">
        <div className="legend small">
          <span><i style={{ background: colors.sender }} /> Sender</span>
          <span><i style={{ background: colors.receiver }} /> Receiver</span>
          <span><i style={{ background: colors.flagged }} /> In a network finding</span>
          <span><i className="line" style={{ background: colors.investigated }} /> Investigated transfer</span>
          {view.truncated && <Badge tone="warn">Showing {view.edges.length} of {view.total_edges} transfers</Badge>}
        </div>
        <div ref={wrap} className="graph-canvas" aria-label="Account network graph">
          {view.nodes.length > 0 ? (
            <ForceGraph2D
              ref={fg}
              graphData={data}
              width={width}
              height={460}
              backgroundColor="rgba(0,0,0,0)"
              nodeId="id"
              nodeRelSize={5}
              nodeVal={(n: GNode) => (n.roles.includes("SENDER") || n.roles.includes("RECEIVER") ? 3 : 1 + n.patterns.length * 0.5)}
              nodeColor={(n: GNode) => (focusNodes && !focusNodes.has(n.id) ? colors.other + "55" : nodeColor(n))}
              nodeLabel={(n: GNode) => escapeHtml(`${n.id}${n.roles.length ? ` · ${n.roles.join(", ")}` : ""}${n.patterns.length ? ` · ${n.patterns.join(", ")}` : ""}`)}
              nodeCanvasObjectMode={() => "after"}
              nodeCanvasObject={(n: GNode, ctx: CanvasRenderingContext2D, scale: number) => {
                if (scale < 1.2 && !(n.roles.includes("SENDER") || n.roles.includes("RECEIVER") || n.id === selected)) return;
                ctx.font = `${11 / scale}px system-ui, sans-serif`;
                ctx.fillStyle = colors.text;
                ctx.textAlign = "center";
                ctx.fillText(n.id.replace(/^ACC_IND_/, "…"), n.x ?? 0, (n.y ?? 0) + 12 / scale);
                if (n.id === selected) {
                  ctx.strokeStyle = colors.highlight;
                  ctx.lineWidth = 2 / scale;
                  ctx.beginPath();
                  ctx.arc(n.x ?? 0, n.y ?? 0, 9 / scale + 4, 0, 2 * Math.PI);
                  ctx.stroke();
                }
              }}
              linkColor={(l: GLink) => (l.investigated ? colors.investigated : l.patterns.length ? colors.linkFlag : colors.link)}
              linkWidth={(l: GLink) => (l.investigated ? 3 : l.patterns.length ? 1.5 : 0.8)}
              linkDirectionalArrowLength={4}
              linkDirectionalArrowRelPos={0.9}
              linkCurvature={0.12}
              linkLabel={(l: GLink) => escapeHtml(`${endId(l.source)} → ${endId(l.target)} · ${formatAmount(l.amount, l.currency)}`
                + `${l.timestamp_utc ? ` · ${formatDateTime(l.timestamp_utc)}` : ""}${l.patterns.length ? ` · ${l.patterns.join(", ")}` : ""}`)}
              onNodeClick={(n: GNode) => setSelected(n.id === selected ? null : n.id)}
              onBackgroundClick={() => setSelected(null)}
              cooldownTicks={120}
              onEngineStop={() => {
                if (!fitted.current) { fg.current?.zoomToFit(400, 40); fitted.current = true; }
              }}
            />
          ) : <p className="empty">No accounts to draw.</p>}
        </div>
        <p className="fineprint">{view.note}</p>
      </div>
      <aside className="network-side">
        {sel ? (
          <div>
            <h3 className="mono">{sel.id}</h3>
            <p>{sel.roles.map((r) => <Badge key={r}>{humanize(r)}</Badge>)}</p>
            {sel.patterns.length > 0 && <p className="small">Patterns: {sel.patterns.map(humanize).join(", ")}</p>}
            <h4>Transfers ({selEdges.length})</h4>
            <ul className="small transfers">
              {selEdges.slice(0, 25).map((e) => (
                <li key={e.id} className={e.investigated ? "investigated" : ""}>
                  {e.source === sel.id ? `→ ${e.target}` : `← ${e.source}`} · {formatAmount(e.amount, e.currency)}
                  <div className="muted">{formatDateTime(e.timestamp_utc)}{e.channel ? ` · ${e.channel}` : ""}</div>
                </li>
              ))}
            </ul>
            <button className="btn btn-ghost btn-xs" onClick={() => setSelected(null)}>Clear selection</button>
          </div>
        ) : (
          <>
            <h3>Network findings ({view.findings.length})</h3>
            {view.findings.length === 0 && <p className="muted small">Agent 3 found no network pattern ({view.agent3_status}).</p>}
            <ul className="findings">
              {view.findings.map((f) => (
                <li key={f.finding_id}>
                  <button className={`finding ${finding === f.finding_id ? "finding-on" : ""}`}
                          onClick={() => setFinding(finding === f.finding_id ? null : f.finding_id)}>
                    <strong>{humanize(f.pattern_type)}</strong>
                    {f.heuristic_score !== null && <span className="muted"> · heuristic {f.heuristic_score.toFixed(2)}</span>}
                    <div className="small">{f.explanation}</div>
                    <div className="small muted mono">{f.rule_id}</div>
                  </button>
                </li>
              ))}
            </ul>
            {view.agent3_warnings.map((w, i) => <p key={i} className="note note-warn small">{w}</p>)}
            <p className="small muted">Click an account for its transfers; click a finding to highlight its accounts.</p>
          </>
        )}
      </aside>
    </div>
  );
}
