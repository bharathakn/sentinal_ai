import type { NetworkEdge, NetworkView } from "../../lib/types";

export const FLOW_W = 860;
export const FLOW_H = 390;
const MAX_LINKS = 48;

export interface FlowNode { id: string; x: number; y: number; step: number; role: "sender" | "receiver" | "flagged" | "other" }
export interface FlowLink { id: string; d: string; step: number; investigated: boolean; flagged: boolean; count: number }

/** Money flows left to right: upstream of the sender, downstream of the receiver. Only stored transfers are drawn. */
export function layoutFlow(view: NetworkView) {
  const pairs = new Map<string, { source: string; target: string; edges: NetworkEdge[] }>();
  for (const e of view.edges) {
    const key = `${e.source}>${e.target}`;
    if (!pairs.has(key)) pairs.set(key, { source: e.source, target: e.target, edges: [] });
    pairs.get(key)!.edges.push(e);
  }
  const all = [...pairs.values()];
  const links = all.slice(0, MAX_LINKS); // the API lists the investigated and finding-linked transfers first
  const s = view.sender_account_id;
  const r = view.receiver_account_id;

  const col = new Map<string, number>();
  if (s) col.set(s, 0);
  if (r && !col.has(r)) col.set(r, 1);
  const queue = [r, s].filter((x): x is string => !!x);
  for (let i = 0; i < queue.length; i++) {
    const n = queue[i];
    for (const l of links) {
      const next = l.source === n ? l.target : l.target === n ? l.source : null;
      if (!next || col.has(next)) continue;
      col.set(next, col.get(n)! + (l.source === n ? 1 : -1));
      queue.push(next);
    }
  }
  for (const l of links) for (const id of [l.source, l.target]) if (!col.has(id)) col.set(id, 1);

  const columns = new Map<number, string[]>();
  for (const [id, c] of col) columns.set(c, [...(columns.get(c) ?? []), id]);
  const keys = [...columns.keys()].sort((a, b) => a - b);
  const flagged = new Set(view.nodes.filter((n) => n.patterns.length).map((n) => n.id));
  const pos = new Map<string, FlowNode>();
  keys.forEach((c, i) => {
    const ids = [...columns.get(c)!];
    const anchor = ids.findIndex((id) => id === s || id === r);
    if (anchor >= 0) ids.splice(Math.floor((ids.length - 1) / 2), 0, ids.splice(anchor, 1)[0]);
    ids.forEach((id, j) => pos.set(id, {
      id,
      x: keys.length === 1 ? FLOW_W / 2 : 70 + (i * (FLOW_W - 140)) / (keys.length - 1),
      // A small offset per column keeps straight chains from sitting on one line.
      y: 26 + ((j + 0.5) * (FLOW_H - 70)) / ids.length + (ids.length === 1 && anchor < 0 ? (i % 2 ? 34 : -34) : 0),
      step: c <= 0 ? -c + 1 : c,
      role: id === s ? "sender" : id === r ? "receiver" : flagged.has(id) ? "flagged" : "other",
    }));
  });

  const drawn: FlowLink[] = links.filter((l) => l.source !== l.target).map((l) => {
    const a = pos.get(l.source)!;
    const b = pos.get(l.target)!;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const len = Math.hypot(dx, dy) || 1;
    const bend = dx > 0 ? 0.1 * len : 0.28 * Math.max(len, 90); // flows running backwards arc wider
    const cx = (a.x + b.x) / 2 + (dy / len) * bend;
    const cy = (a.y + b.y) / 2 - (dx / len) * bend;
    const end = Math.hypot(b.x - cx, b.y - cy) || 1;
    const ex = b.x - ((b.x - cx) / end) * 16;
    const ey = b.y - ((b.y - cy) / end) * 16;
    return {
      id: `${l.source}>${l.target}`,
      d: `M${a.x},${a.y} Q${cx},${cy} ${ex},${ey}`,
      step: Math.max(a.step, b.step),
      investigated: l.edges.some((e) => e.investigated),
      flagged: l.edges.some((e) => e.patterns.length > 0),
      count: l.edges.length,
    };
  });
  return { nodes: [...pos.values()], links: drawn, hidden: all.length - links.length };
}
