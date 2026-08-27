"""
Research surface — §27, behind `RESEARCH_READ`.

**Why it exists.** A researcher role that has no endpoint is a role that cannot
be demonstrated, and a research dashboard assembled in the browser out of
`/api/health` and `/api/intel/*` would be a researcher reading the investigator
surfaces — which is precisely what §27 says must not happen ("Do not expose raw
personally identifiable information"). One endpoint, one permission, and one
place where the aggregation is done.

**What it consumes.** The fraud graph's own statistics, the model card's
evaluation block, and the promotion-gate comparison file. Nothing else — in
particular it never touches `investigations`, `case_records` or `users`.

**What it outputs.** Counts, distributions and measured scores.

**What is deliberately absent.** Every field that could identify a person or a
case: no case ids, no phone numbers, no UPI IDs, no email addresses, no city
finer than the state rollup the public awareness endpoint already publishes, and
no free text from any submission. `_anonymised_trends` builds its rows from the
graph's cluster summaries by reading only the scam type, the size and the risk
band, so there is no path from this response back to an individual.

**How it is evaluated.** `test_rbac.py` asserts a researcher reaches this and
reaches no case-level route, and that the payload contains none of the fields
listed above.

**Limitations, stated.** "Anonymised" here means *aggregated and stripped* — the
counts are real counts over real clusters, and a cluster of size 1 in a rare
scam type in a small state is, in principle, re-identifiable by someone who
already knows the case exists. Clusters below `_MIN_CLUSTER` are therefore
withheld rather than published; that is a threshold, not a formal privacy
guarantee, and this project does not claim differential privacy.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from ..auth import require_permission
from ..engine import classifier as classifier_mod
from ..engine.classifier import load_classifier
from ..engine.twin import DigitalTwin
from ..intel import get_intel
from ..models_db import User

router = APIRouter(prefix="/api/research", tags=["research"])

#: Clusters smaller than this are counted but never listed. A cluster of one is
#: one case, and publishing its scam type and state is publishing that case.
_MIN_CLUSTER = 3


def _comparison() -> Dict[str, Any]:
    """The measured macro-F1 of both classifier backends, if the promotion gate
    has been run. Empty when it has not — an unmeasured model reports nothing
    rather than a plausible number."""
    path = classifier_mod.COMPARISON_PATH
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _anonymised_trends(graph: Any) -> List[Dict[str, Any]]:
    """Fraud trends as (scam type, cluster count, cases, mean risk) rows.

    Built from cluster summaries, never from cases, and never carrying an
    identifier of any kind — read the loop below and note that nothing from
    `c.shared_phones`, `c.shared_upi_ids` or `c.cluster_id` is copied out.
    """
    by_type: Dict[str, Dict[str, Any]] = {}
    for c in graph.clusters:
        if c.size < _MIN_CLUSTER:
            continue
        row = by_type.setdefault(
            c.primary_scam,
            {
                "scam_type": c.primary_scam,
                "scam_name": c.primary_scam_name,
                "clusters": 0,
                "cases": 0,
                "loss_inr": 0,
                "_risk_sum": 0.0,
            },
        )
        row["clusters"] += 1
        row["cases"] += c.size
        row["loss_inr"] += int(c.total_loss_inr or 0)
        row["_risk_sum"] += float(c.mean_threat or 0.0)
    out = []
    for row in by_type.values():
        risk_sum = row.pop("_risk_sum")
        row["mean_threat"] = round(risk_sum / max(1, row["clusters"]), 1)
        out.append(row)
    return sorted(out, key=lambda r: r["cases"], reverse=True)


@router.get("/overview")
def overview(_: User = Depends(require_permission("RESEARCH_READ"))) -> Dict[str, Any]:
    """Dataset statistics, model evaluation, and anonymised fraud trends.

    Every number is read from something that was actually computed — the graph
    that is serving, the classifier that is loaded, the comparison file the
    promotion gate wrote. Where a measurement has not been made the field is
    empty and the `measured` flag says so, because an unevaluated capability
    reported as a score is the exact failure the model card exists to prevent.
    """
    graph = get_intel().graph()
    stats = graph.stats()
    classifier = load_classifier()
    twin = DigitalTwin()
    comparison = _comparison()

    withheld = sum(1 for c in graph.clusters if c.size < _MIN_CLUSTER)
    return {
        "dataset": {
            "cases": stats["total_cases"],
            "clusters": stats["active_clusters"],
            "campaigns": stats["campaigns"],
            "linked_entities": stats["linked_entities"],
            "graph_nodes": stats["graph_nodes"],
            "graph_edges": stats["graph_edges"],
            "total_loss_inr": stats["total_loss_inr"],
        },
        "model": {
            "task": "8-way utterance classification over the scam-call arc",
            "base_model": "google/muril-base-cased",
            "serving": classifier.backend,
            "checkpoint_backed": classifier.checkpoint_backed,
            "serving_best": not classifier_mod.serving_is_fallback,
            "selection_reason": classifier_mod.selection_reason,
        },
        "evaluation": {
            "protocol": "macro-F1 on four whole held-out call archetypes, both "
                        "backends scored through the same serving interface "
                        "(ml/evaluation/eval_backends.py)",
            "measured": bool(comparison),
            "scores": comparison,
        },
        "twin": {
            "kind": "first-order Markov over collapsed stage runs",
            "fitted": not twin.degraded,
            "stages": sorted(twin.transitions.keys()),
            "support": twin.support,
        },
        "trends": _anonymised_trends(graph),
        "privacy": {
            "min_cluster_size": _MIN_CLUSTER,
            "clusters_withheld": withheld,
            "note": "Aggregates only. No case identifier, phone number, UPI ID, "
                    "email address or submitted text appears in this response, "
                    f"and clusters smaller than {_MIN_CLUSTER} cases are withheld "
                    "rather than published.",
        },
    }


__all__ = ["router"]
