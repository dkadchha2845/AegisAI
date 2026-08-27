"""
FIGAE routes (Module 2) — the investigator dashboard's backend.

Read-only intelligence over the fraud graph: live stats, clusters, one cluster's
network subgraph, geospatial hotspots, centrality, link predictions, entity
search, and the AI investigation report for a cluster. Every response is derived
from the cached graph, so a poll is cheap.

**The surface splits in two, and the split is the whole access-control story
here.** `THREAT_INTEL_READ` covers the *aggregate* views — counts, state-level
totals, city-level dots — which carry no identifier belonging to any person and
are what the landing page and a citizen's home have always shown everybody.
`GRAPH_READ` covers the *entity-level* views — clusters and their members,
centrality over reused phone numbers and UPI IDs, link prediction, entity
search, the raw graph — which are personal data about specific accounts and
belong to investigators. A citizen holds the first and not the second, which is
a distinction the old uniform `require_role("viewer")` could not make.

The one write path is implicit: saving a Module 1 case (in `routes/reports.py`)
rebuilds the graph, so this surface reflects new detections without its own
mutation endpoint. That keeps Module 2 a pure consumer of Module 1, which is the
architecture the PDF argues for.
"""

from __future__ import annotations

from itertools import islice
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import require_permission
from ..intel import get_intel
from ..intel.report import enhance_narrative, investigation_report
from ..models_db import User

router = APIRouter(prefix="/api/intel", tags=["intel"])


@router.get("/stats")
def intel_stats(_: User = Depends(require_permission("THREAT_INTEL_READ"))) -> Dict[str, Any]:
    """Live statistics for the dashboard header: active clusters, campaigns,
    total cases, linked entities, exposure."""
    return get_intel().graph().stats()


@router.get("/clusters")
def list_clusters(_: User = Depends(require_permission("GRAPH_READ"))) -> Dict[str, Any]:
    """All fraud clusters, worst-risk first."""
    g = get_intel().graph()
    return {"clusters": [c.as_dict() for c in g.clusters]}


@router.get("/clusters/{cluster_id}")
def cluster_detail(
    cluster_id: str, _: User = Depends(require_permission("GRAPH_READ"))
) -> Dict[str, Any]:
    """One cluster: its summary, its network subgraph, and the AI investigation
    report."""
    g = get_intel().graph()
    cluster = next((c for c in g.clusters if c.cluster_id == cluster_id), None)
    if cluster is None:
        raise HTTPException(status_code=404, detail=f"No cluster {cluster_id}")
    report = investigation_report(cluster)
    prose = enhance_narrative(report)
    if prose:
        report["narrative_llm"] = prose
    return {
        "cluster": cluster.as_dict(),
        "graph": g.export_subgraph(cluster_id),
        "report": report,
    }


@router.get("/clusters/{cluster_id}/report")
def cluster_report(
    cluster_id: str, _: User = Depends(require_permission("GRAPH_READ"))
) -> Dict[str, Any]:
    """Just the AI investigation report for a cluster (the FC-021 exemplar)."""
    g = get_intel().graph()
    cluster = next((c for c in g.clusters if c.cluster_id == cluster_id), None)
    if cluster is None:
        raise HTTPException(status_code=404, detail=f"No cluster {cluster_id}")
    report = investigation_report(cluster)
    prose = enhance_narrative(report)
    if prose:
        report["narrative_llm"] = prose
    return report


@router.get("/geo")
def geospatial(_: User = Depends(require_permission("THREAT_INTEL_READ"))) -> Dict[str, Any]:
    """State / district / city hotspots for the command-centre map."""
    from ..intel.geo import hotspots

    g = get_intel().graph()
    return hotspots([c.as_dict() for c in g.cases])


@router.get("/points")
def geo_points(_: User = Depends(require_permission("THREAT_INTEL_READ"))) -> Dict[str, Any]:
    """Per-case map points — the granular layer under the aggregated hotspots.

    Each case that resolves to a known city becomes one dated, geo-located
    marker, so the interactive map can cluster individual reports and filter
    them by scam type and by date. Cases whose city is not in the gazetteer are
    dropped rather than placed at a guessed centroid — a marker in the wrong
    place is worse than one fewer marker.
    """
    from ..intel.geo import CITIES
    from ..intel.repository import scam_name

    g = get_intel().graph()
    points: List[Dict[str, Any]] = []
    scam_types: Dict[str, str] = {}
    for c in g.cases:
        row = CITIES.get(c.city or "")
        if not row:
            continue
        lat, lon = row[0], row[1]
        scam_types[c.scam_type] = scam_name(c.scam_type)
        points.append(
            {
                "id": c.case_id,
                "lat": lat,
                "lon": lon,
                "city": c.city,
                "state": c.state,
                "scam_type": c.scam_type,
                "scam_name": scam_name(c.scam_type),
                "risk": c.threat_level,
                "amount_inr": c.amount_inr,
                "reported_at": c.reported_at,
            }
        )
    return {
        "points": points,
        "scam_types": [{"id": k, "name": v} for k, v in sorted(scam_types.items())],
    }


@router.get("/centrality")
def centrality(_: User = Depends(require_permission("GRAPH_READ"))) -> Dict[str, Any]:
    """Most-reused fraud entities — the freeze-first choke points."""
    return {"entities": get_intel().graph().centrality()}


@router.get("/links")
def link_predictions(_: User = Depends(require_permission("GRAPH_READ"))) -> Dict[str, Any]:
    """Predicted hidden links: numbers joined through a shared payment account."""
    return {"predictions": get_intel().graph().link_predictions()}


@router.get("/search")
def entity_search(
    q: str = Query(min_length=2, max_length=128),
    _: User = Depends(require_permission("GRAPH_READ")),
) -> Dict[str, Any]:
    """Search by phone / UPI / wallet / email / case id."""
    return get_intel().search(q)


@router.get("/graph")
def full_graph(
    limit: int = Query(default=300, le=1200),
    _: User = Depends(require_permission("GRAPH_READ")),
) -> Dict[str, Any]:
    """A capped view of the whole knowledge graph for the overview visualisation.

    Nodes are coloured by kind and sized by reuse; capped so the canvas is not
    asked to lay out thousands of nodes. The per-cluster subgraph is the detailed
    view; this is the 'everything at once' backdrop.
    """
    g = get_intel().graph()
    nodes = []
    edges = []
    # islice states the cap directly, instead of a counter plus a break.
    for n, d in islice(g.G.nodes(data=True), limit):
        kind = d.get("kind")
        nodes.append({
            "id": n,
            "kind": kind,
            "label": d.get("value") or d.get("case_id"),
            "cases": d.get("uses", 1) if kind != "case" else None,
            "threat": d.get("threat"),
            "cluster": g._cluster_of.get(d.get("case_id")) if kind == "case" else None,
        })
    node_ids = {n["id"] for n in nodes}
    for u, v in g.G.edges():
        if u in node_ids and v in node_ids:
            edges.append({"source": u, "target": v})
    return {"nodes": nodes, "edges": edges, "truncated": g.G.number_of_nodes() > limit}
