"""
FIGAE (Module 2) regression tests.

The properties that must hold for the fraud-intelligence view to be trustworthy:
the seed builds real clusters, reused infrastructure is what links them, the
cross-crew money mule is found by link prediction, risk scoring is monotonic in
the factors it claims to use, and isolated cases are NOT folded into a campaign.
"""

from __future__ import annotations

from services.api.intel.graph import FraudGraph
from services.api.intel.repository import seed_cases
from services.api.intel.scoring import band, score_cluster


def _graph() -> FraudGraph:
    return FraudGraph(seed_cases())


def test_seed_is_deterministic():
    a = [c.case_id for c in seed_cases()]
    b = [c.case_id for c in seed_cases()]
    assert a == b and len(a) > 100


def test_clusters_form_from_shared_infrastructure():
    g = _graph()
    assert len(g.clusters) >= 6
    # The worst cluster is the digital-arrest campaign: many cases, several
    # shared numbers and UPIs, multiple states — the PDF's FC-021 shape.
    top = g.clusters[0]
    assert top.size >= 10
    assert top.risk == "CRITICAL"
    assert len(top.shared_phones) >= 2
    assert len(top.shared_upi_ids) >= 2
    assert len(top.states) >= 2


def test_link_prediction_finds_shared_payment_account():
    """The PDF's canonical example: two different phone numbers joined through a
    shared payment account, without ever appearing on the same case."""
    g = _graph()
    preds = g.link_predictions()
    assert preds, "expected at least one hidden link"
    for p in preds:
        assert p["source"] != p["target"]
        assert p["via"], "a predicted link must name the shared infrastructure"
        assert 0.5 <= p["confidence"] <= 0.98


def test_centrality_surfaces_reused_entities():
    g = _graph()
    rows = g.centrality()
    assert rows
    # Every centrality row is reused (>=2 cases) — a once-seen entity is not a
    # choke point.
    assert all(r["cases"] >= 2 for r in rows)
    # Ranked most-reused first.
    assert rows == sorted(rows, key=lambda r: -r["cases"])


def test_risk_scoring_is_monotonic():
    low, low_band = score_cluster(
        n_cases=2, total_loss=10_000, shared_infra=0, n_states=1,
        peak_threat=40, mean_threat=30,
    )
    high, high_band = score_cluster(
        n_cases=40, total_loss=8_000_000, shared_infra=8, n_states=5,
        peak_threat=96, mean_threat=88,
    )
    assert high > low
    assert high_band == "CRITICAL"
    assert low_band in ("LOW", "MEDIUM")


def test_band_thresholds():
    assert band(80) == "CRITICAL"
    assert band(60) == "HIGH"
    assert band(40) == "MEDIUM"
    assert band(10) == "LOW"


def test_isolated_cases_are_not_clustered():
    """The 6 deliberately-isolated seed cases must not appear in any cluster — a
    network engine that finds a campaign in everything is untrustworthy."""
    g = _graph()
    clustered = {cid for cl in g.clusters for cid in cl.case_ids}
    # Isolated cases carry unique random phones/UPIs, so none should be clustered.
    isolated_scams = {"sim_swap_trai", "refund_overpayment", "job_offer_fee"}
    for case in g.cases:
        if case.scam_type in isolated_scams:
            assert case.case_id not in clustered


def test_search_finds_case_and_entity():
    g = _graph()
    from services.api.intel.service import IntelService

    svc = IntelService()
    svc._graph = g
    # A shared UPI resolves to its cluster.
    res = svc.search("customs.duty@okaxis")
    assert res["matches"], "shared UPI should be found"
    assert res["matches"][0]["case_count"] >= 2


def test_hotspots_place_states_with_coordinates():
    from services.api.intel.geo import hotspots

    g = _graph()
    hs = hotspots([c.as_dict() for c in g.cases])
    assert hs["states"]
    for h in hs["states"]:
        assert h["lat"] and h["lon"]
        assert h["risk"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    # Sorted most-cases-first.
    counts = [h["cases"] for h in hs["states"]]
    assert counts == sorted(counts, reverse=True)
