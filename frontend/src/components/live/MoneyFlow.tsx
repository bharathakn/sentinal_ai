import { useMemo } from "react";
import { prefersReducedMotion } from "../../lib/motion";
import type { NetworkView } from "../../lib/types";
import { FLOW_H, FLOW_W, layoutFlow } from "./moneyFlowLayout";

export function MoneyFlow({ view }: { view: NetworkView }) {
  const { nodes, links, hidden } = useMemo(() => layoutFlow(view), [view]);
  const moving = !prefersReducedMotion();
  return (
    <figure className="flow">
      <svg viewBox={`0 0 ${FLOW_W} ${FLOW_H}`} role="img"
           aria-label={`Money flow across ${nodes.length} accounts and ${links.length} connections`}>
        <defs>
          {["base", "flag", "hot"].map((k) => (
            <marker key={k} id={`arrow-${k}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7"
                    markerUnits="userSpaceOnUse" orient="auto">
              <path d="M0,0 L10,5 L0,10 z" className={`arrow-${k}`} />
            </marker>
          ))}
        </defs>
        {links.map((l) => {
          const kind = l.investigated ? "hot" : l.flagged ? "flag" : "base";
          const delay = l.investigated ? 0 : l.step * 0.22;
          return (
            <g key={l.id}>
              <path d={l.d} pathLength={1} className={`flow-link link-${kind}`} style={{ animationDelay: `${delay}s` }}
                    markerEnd={`url(#arrow-${kind})`} />
              {moving && kind !== "base" && (
                <circle r={kind === "hot" ? 4.5 : 3} className={`coin coin-${kind}`} style={{ animationDelay: `${delay + 0.5}s` }}>
                  <animateMotion dur={kind === "hot" ? "1.5s" : "2.3s"} repeatCount="indefinite" path={l.d} />
                </circle>
              )}
            </g>
          );
        })}
        {nodes.map((n) => (
          <g key={n.id} transform={`translate(${n.x},${n.y})`}>
            <g className={`flow-node node-${n.role}`}
               style={{ animationDelay: `${n.role === "sender" || n.role === "receiver" ? 0 : n.step * 0.22}s` }}>
              <title>{n.id}</title>
              {(n.role === "sender" || n.role === "receiver") && <circle r="21" className="halo" />}
              <circle r={n.role === "sender" || n.role === "receiver" ? 13 : 9} className="dot" />
              <text y={n.role === "sender" || n.role === "receiver" ? 35 : 24}>
                {n.id.length > 12 ? `…${n.id.slice(-6)}` : n.id}
              </text>
              {(n.role === "sender" || n.role === "receiver") && <text y="-27" className="role">{n.role}</text>}
            </g>
          </g>
        ))}
      </svg>
      <figcaption>
        <span><i className="key k-sender" />Sender</span>
        <span><i className="key k-receiver" />Receiver</span>
        <span><i className="key k-flag" />In a suspicious pattern</span>
        {hidden > 0 && <span>{hidden} more connections in the case file</span>}
      </figcaption>
    </figure>
  );
}
