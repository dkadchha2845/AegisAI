"""
FIGAE service — the cached, rebuildable intelligence layer the routes call.

Holds one `FraudGraph` built from the historical seed plus every Module 1
detection ingested so far, and rebuilds it on write rather than per request: a
dashboard poll is a dict read, and the expensive graph construction happens once
when a new case actually arrives. This is the "continuously evolving" repository
the PDF describes — the graph the investigator sees this afternoon includes the
call Module 1 detected this morning.

Thread-safety: FastAPI serves sync routes from a threadpool, so the rebuild is
guarded by a lock and readers get a consistent snapshot (the reference is swapped
atomically after a full rebuild, never mutated in place).
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from .entities import _norm_phone, entity_key
from .graph import FraudGraph
from .repository import FraudCase, ingest_case_records, seed_cases


class IntelService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._live_cases: List[FraudCase] = []
        self._graph: Optional[FraudGraph] = None

    # -- lifecycle ---------------------------------------------------------

    def graph(self) -> FraudGraph:
        """Current graph, built lazily on first access."""
        if self._graph is None:
            self.rebuild()
        assert self._graph is not None
        return self._graph

    def rebuild(self, extra_records: Optional[List[Dict[str, Any]]] = None) -> FraudGraph:
        """Rebuild from seed + live Module 1 cases (+ any newly supplied records).

        `extra_records` are `CaseRecord.package_json` blobs; they are ingested,
        appended to the live set, and the whole graph is recomputed. Called from
        the reports route when a case is saved, so Module 1 → Module 2 is
        automatic.
        """
        with self._lock:
            if extra_records:
                new = ingest_case_records(extra_records)
                # De-dup by case_id so re-saving a report does not double it.
                have = {c.case_id for c in self._live_cases}
                self._live_cases.extend(c for c in new if c.case_id not in have)
            all_cases = seed_cases() + self._live_cases
            self._graph = FraudGraph(all_cases)
            return self._graph

    def ingest_package(self, package: Dict[str, Any], *, city: Optional[str] = None) -> None:
        """Add a single Module 1 / Module 3 detection and rebuild."""
        from .repository import case_from_package

        with self._lock:
            case = case_from_package(package, city=city)
            if case.case_id not in {c.case_id for c in self._live_cases}:
                self._live_cases.append(case)
            all_cases = seed_cases() + self._live_cases
            self._graph = FraudGraph(all_cases)

    # -- search ------------------------------------------------------------

    def search(self, query: str) -> Dict[str, Any]:
        """Entity search: phone / UPI / wallet / email / case id. Returns the
        matching entity, the cases that touch it, and the cluster it belongs to —
        the investigator's 'who else is this number connected to?' lookup."""
        g = self.graph()
        q = query.strip()
        if not q:
            return {"query": query, "matches": []}

        # Case id lookup first — exact.
        if q.upper() in g.by_id or q in g.by_id:
            case = g.by_id.get(q) or g.by_id.get(q.upper())
            return {
                "query": query,
                "kind": "case",
                "matches": [self._case_view(case, g)] if case else [],
            }

        candidates: List[str] = []
        digits = _norm_phone(q)
        if len(digits) == 10:
            candidates.append(entity_key("phone", digits))
        for kind in ("upi", "wallet", "email", "bank", "domain"):
            candidates.append(entity_key(kind, q))

        matches: List[Dict[str, Any]] = []
        for enode in candidates:
            if enode in g.G:
                data = g.G.nodes[enode]
                case_ids = [g.G.nodes[n]["case_id"] for n in g.G.neighbors(enode)]
                clusters = sorted({
                    g._cluster_of[cid] for cid in case_ids if cid in g._cluster_of
                })
                matches.append({
                    "kind": data.get("kind"),
                    "value": data.get("value"),
                    "cases": case_ids,
                    "case_count": len(case_ids),
                    "clusters": clusters,
                })

        # Fuzzy fallback: substring over entity values, so a partial UPI still
        # finds something.
        if not matches:
            ql = q.lower()
            for node, data in g.G.nodes(data=True):
                if data.get("kind") in ("phone", "upi", "wallet", "email", "bank", "domain"):
                    val = str(data.get("value", "")).lower()
                    if ql in val:
                        case_ids = [g.G.nodes[n]["case_id"] for n in g.G.neighbors(node)]
                        matches.append({
                            "kind": data.get("kind"),
                            "value": data.get("value"),
                            "cases": case_ids,
                            "case_count": len(case_ids),
                            "clusters": sorted({
                                g._cluster_of[cid] for cid in case_ids if cid in g._cluster_of
                            }),
                        })
                if len(matches) >= 10:
                    break

        matches.sort(key=lambda m: -m["case_count"])
        return {"query": query, "matches": matches[:10]}

    def _case_view(self, case: FraudCase, g: FraudGraph) -> Dict[str, Any]:
        return {
            **case.as_dict(),
            "cluster": g._cluster_of.get(case.case_id),
        }


_service: Optional[IntelService] = None


def get_intel() -> IntelService:
    global _service
    if _service is None:
        _service = IntelService()
    return _service
