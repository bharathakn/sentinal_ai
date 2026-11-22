"""
Sentinel AI — Agent 3 on an isolated, in-memory transfer graph.

Used for uploaded datasets. The shared Neo4j graph is keyed by account id and
Agent 3's MERGE overwrites matching transfers, so uploaded rows must neither
be written to it nor draw evidence from it. This module holds the uploaded
rows in memory and answers the same questions as the Agent 3 Cypher queries;
the detectors and thresholds are unchanged.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterable, Iterator, Optional

from ...graph.loader import TransactionGraphLoader
from ...schemas.canonical_transaction import CanonicalTransaction
from .config import Agent3Config
from .network_analyser import NetworkAnalyserAgent

MAX_EXPANSIONS = 200_000
# Every cycle is examined. A small cap would drop real rings arbitrarily: accounts
# in the demo dataset have more than 50 candidate cycles in one window.
MAX_CYCLES = 5_000
_PATH_FIELDS = ("tx_graph_id", "amount", "amount_str", "currency", "timestamp_utc", "channel")
_WINDOW_FIELDS = ("raw_record_id",) + _PATH_FIELDS


class GraphSearchLimit(Exception):
    """A path search was too large; Agent 3 reports that detector as skipped."""


class InMemoryTransferGraph:
    def __init__(self, transactions: Iterable[CanonicalTransaction] = ()) -> None:
        self._out: dict[str, list[dict]] = defaultdict(list)
        self._in: dict[str, list[dict]] = defaultdict(list)
        self._by_id: dict[tuple[str, str], dict] = {}
        self.accounts: set[str] = set()
        for tx in transactions:
            self.add(tx)

    def add(self, tx: CanonicalTransaction) -> None:
        src, dst = tx.sender.account_id, tx.receiver.account_id
        if not (src and dst):
            return
        self.accounts.update((src, dst))
        params = TransactionGraphLoader._params(tx)  # same property mapping as the Neo4j loader
        key = (src, params["tx_graph_id"])
        if key in self._by_id:
            return
        edge = {"src": src, "dst": dst, **{f: params[f] for f in _WINDOW_FIELDS}}
        self._by_id[key] = edge
        self._out[src].append(edge)
        self._in[dst].append(edge)

    @property
    def transfer_count(self) -> int:
        return len(self._by_id)

    def window(self, account_id: str, direction: str, from_ts: str, to_ts: str, limit: int) -> list[dict]:
        side, other = (self._out, "dst") if direction == "out" else (self._in, "src")
        found = sorted((e for e in side.get(account_id, ())
                        if e["timestamp_utc"] and from_ts <= e["timestamp_utc"] <= to_ts),
                       key=lambda e: e["timestamp_utc"])
        return [{"account_id": account_id, "counterpart_id": e[other], **{f: e[f] for f in _WINDOW_FIELDS}}
                for e in found[:limit]]

    def subject(self, sender_id: str, tx_graph_id: str) -> Optional[dict]:
        return self._by_id.get((sender_id, tx_graph_id))

    def cycles(self, account_id: str, min_len: int, max_len: int, from_ts: str, to_ts: str) -> list[dict]:
        budget = [MAX_EXPANSIONS]

        def walk(node: str, path: list[dict]) -> Iterator[list[dict]]:
            for e in self._out.get(node, ()):
                budget[0] -= 1
                if budget[0] < 0:
                    raise GraphSearchLimit()
                if not e["timestamp_utc"] or not from_ts <= e["timestamp_utc"] <= to_ts:
                    continue
                if any(e is p for p in path):  # Cypher never repeats a relationship in a path
                    continue
                new = path + [e]
                if e["dst"] == account_id and len(new) >= min_len:
                    yield new
                if len(new) < max_len:
                    yield from walk(e["dst"], new)

        out = []
        for path in walk(account_id, []):
            out.append(_path(path, path))
            if len(out) == MAX_CYCLES:
                break
        return out

    def chains(self, r0: dict, direction: str, k: int, from_ts: str, to_ts: str,
               retention: float, max_gap_s: int) -> list[dict]:
        """Chains grown hop by hop from r0; each hop must satisfy time, retention and gap."""
        t0 = r0["timestamp_utc"]
        if not t0:
            return []
        forward = direction == "forward"
        budget = [MAX_EXPANSIONS]
        found: list[list[dict]] = []

        def linked(earlier: dict, later: dict) -> bool:
            a, b = earlier["timestamp_utc"], later["timestamp_utc"]
            if not (a and b) or b <= a or earlier["amount"] is None or later["amount"] is None:
                return False
            return (later["amount"] >= retention * earlier["amount"]
                    and int((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()) <= max_gap_s)

        def walk(node: str, last: dict, rels: list[dict]) -> None:
            for e in (self._out if forward else self._in).get(node, ()):
                budget[0] -= 1
                if budget[0] < 0:
                    raise GraphSearchLimit()
                t = e["timestamp_utc"]
                if not t or not (t0 < t <= to_ts if forward else from_ts <= t < t0):
                    continue
                if not (linked(last, e) if forward else linked(e, last)):
                    continue
                new = rels + [e] if forward else [e] + rels
                found.append(new)
                if len(new) < k:
                    walk(e["dst"] if forward else e["src"], e, new)

        walk(r0["dst"] if forward else r0["src"], r0, [])
        found.sort(key=len, reverse=True)
        return [_path(rels, [r0] + rels if forward else rels) for rels in found[:25]]


def _path(rels: list[dict], transfers: list[dict]) -> dict:
    return {"node_ids": [rels[0]["src"]] + [e["dst"] for e in rels],
            "transfers": [{f: e[f] for f in _PATH_FIELDS} for e in transfers]}


class DatasetNetworkAnalyserAgent(NetworkAnalyserAgent):
    """Agent 3 over one uploaded dataset. Has no path to Neo4j."""

    def __init__(self, graph: InMemoryTransferGraph, config: Optional[Agent3Config] = None) -> None:
        super().__init__(config=config, connection_manager=graph)

    def _ingest_subject(self, mgr, transaction) -> bool:
        return False  # the dataset already contains it; nothing is written

    def _account_exists(self, mgr, account_id) -> bool:
        return account_id in mgr.accounts

    def _fetch_transfer_count(self, mgr) -> list[dict]:
        return [{"transfers": mgr.transfer_count}]

    def _fetch_window(self, mgr, direction, **p) -> list[dict]:
        return mgr.window(p["account_id"], direction, p["from_ts"], p["to_ts"], p["limit"])

    def _fetch_cycles(self, mgr, *, min_len, max_len, **p) -> list[dict]:
        return mgr.cycles(p["account_id"], min_len, max_len, p["from_ts"], p["to_ts"])

    def _fetch_chains(self, mgr, direction, *, k, **p) -> list[dict]:
        r0 = mgr.subject(p["sender_id"], p["tx_graph_id"])
        if r0 is None:
            return []
        return mgr.chains(r0, direction, k, p["from_ts"], p["to_ts"], p["retention"], p["max_gap_s"])

    @staticmethod
    def _run(mgr, cypher, **params):
        raise RuntimeError("An uploaded dataset must never query the shared graph.")


__all__ = ["DatasetNetworkAnalyserAgent", "InMemoryTransferGraph", "GraphSearchLimit"]
