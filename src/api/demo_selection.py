"""
Sentinel AI — which flagged transactions the demo investigates.

The strongest anomaly signals in the demo dataset are all layering chains, so
"top five" showed five copies of one story. The demo instead takes the
strongest flagged transaction of each suspected pattern, in the order of
LEADS (five different stories first).

No answer key and no agent verdict is involved. A lead comes from the
transaction's own fields and a pre-check with Agent 3's detectors on an
in-memory copy of the dataset. A network pattern counts only when the
transaction is itself one of that pattern's transfers; its account merely
touching one is not enough. Uploads always get the strongest signals.
"""

from __future__ import annotations

from typing import Iterable, Optional

from ..agents.agent3.dataset_graph import DatasetNetworkAnalyserAgent, InMemoryTransferGraph
from ..agents.agent3.output_schema import NetworkPatternType as P
from ..evidence.providers.geolocation import _ANOMALY_DISTANCE_KM
from ..graph.mapping import make_tx_graph_id
from ..schemas.canonical_transaction import CanonicalTransaction

MAX_PRECHECKS = 800  # candidates examined, strongest first
SPIKE_RATIO = 8.0    # times the account's 30-day average
LEADS = ("Layering chain", "Split payments", "Account takeover", "Unusual location", "Sudden large payment",
         "Circular money flow", "Mule account")


def suspected_patterns(tx: CanonicalTransaction, findings: list) -> set[str]:
    """Leads to investigate (not findings) that this transaction is an example of."""
    gid = make_tx_graph_id(tx)
    around, part_of = set(), set()
    for f in findings:
        around.add(f.pattern_type)
        transfers = list(f.supporting_transfers) + [t for p in f.layering_paths for t in p.transfers]
        if any(t.tx_graph_id == gid for t in transfers):
            part_of.add(f.pattern_type)

    md = tx.metadata
    new_payee = bool(md and md.is_new_beneficiary)
    far = bool(md and (md.distance_from_home_km or 0) > _ANOMALY_DISTANCE_KM)
    new_device = bool(tx.device and tx.device.is_new_device)
    layered = P.LAYERING in around

    leads = set()
    if P.LAYERING in part_of:
        leads.add("Layering chain")
    if P.STRUCTURING in part_of and not layered:
        leads.add("Split payments")
    if new_device and new_payee and not far and not part_of & {P.LAYERING, P.STRUCTURING}:
        leads.add("Account takeover")
    if far:
        leads.add("Unusual location")
    if not part_of and not new_payee and not far and md and (md.amount_ratio_vs_30d_avg or 0) >= SPIKE_RATIO:
        leads.add("Sudden large payment")
    if P.SUSPICIOUS_CLUSTER in part_of and not layered:
        leads.add("Circular money flow")
    if P.FAN_IN in part_of and not around & {P.LAYERING, P.STRUCTURING} and P.SUSPICIOUS_CLUSTER not in part_of:
        leads.add("Mule account")
    return leads


def pick_varied(transactions: Iterable[CanonicalTransaction], ranked: list[int],
                count: int) -> list[tuple[int, Optional[str]]]:
    """Return up to ``count`` (row index, lead) pairs from ``ranked`` (strongest first).

    Each lead appears once; if there are fewer leads than ``count``, the strongest
    remaining transactions fill up. The result keeps the strongest-first order.
    """
    # Only the candidates are kept as objects: holding all 10,000 pushed the
    # server to Render's 512 MB limit. The graph needs just the edges.
    candidates = set(ranked[:MAX_PRECHECKS])
    txs: dict[int, CanonicalTransaction] = {}
    graph = InMemoryTransferGraph()
    for index, tx in enumerate(transactions):
        graph.add(tx)
        if index in candidates:
            txs[index] = tx
    tracer = DatasetNetworkAnalyserAgent(graph)
    wanted = list(LEADS[:count])
    chosen: dict[int, Optional[str]] = {}
    for index in ranked[:MAX_PRECHECKS]:
        if not wanted:
            break
        out = tracer({"transaction": txs[index]})["agent3_output"]
        matches = suspected_patterns(txs[index], out.findings)
        lead = next((name for name in wanted if name in matches), None)
        if lead:
            chosen[index] = lead
            wanted.remove(lead)
    for index in ranked:
        if len(chosen) >= count:
            break
        chosen.setdefault(index, None)
    return [(i, chosen[i]) for i in ranked if i in chosen]


__all__ = ["LEADS", "pick_varied", "suspected_patterns"]
