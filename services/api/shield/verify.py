"""
Threat verification layer (CFSRP / Module 3, Step 2).

The citizen submits something suspicious — a message, a caller number, a UPI ID,
a pasted chat — and this fuses the two upstream modules into one answer:

  * **Module 1 (RSSIE)** scores the artifact through the very same analyzer the
    investigator tools use — one implementation, so the citizen and the analyst
    never see different verdicts on the same text.
  * **Module 2 (FIGAE)** is cross-referenced: is this number or UPI already known
    in a fraud cluster? Is the citizen's city a hotspot? A message that scores
    only SUSPICIOUS on its own words becomes a confident warning when the number
    is a node in a 26-case digital-arrest campaign — which is exactly the value
    of connecting the modules.

The output carries the Module 1 verdict, any Module 2 corroboration, stage-aware
guidance, and an emergency response. Low false-positive rate is an explicit
evaluation axis, so Module 2 corroboration *raises* confidence but its absence
never invents danger — an unknown number is unknown, not safe and not damning.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from ..engine.analyzer import analyze_text
from ..intel import get_intel
from .guidance import build_guidance
from .response import build_response


def _intel_match(number: Optional[str], upi: Optional[str], text: str) -> Dict[str, Any]:
    """Cross-reference the submitted identifiers against the FIGAE fraud graph.
    Returns any cluster hits and the linked-entity context."""
    intel = get_intel()
    hits: List[Dict[str, Any]] = []

    def _lookup(value: Optional[str]) -> None:
        if not value:
            return
        res = intel.search(value)
        for m in res.get("matches", []):
            if m.get("clusters"):
                hits.append(m)

    _lookup(number)
    _lookup(upi)
    # Also mine identifiers out of the pasted text (a message often contains the
    # scammer's UPI even when the citizen only pasted the words).
    from ..intel.entities import extract_from_text

    ent = extract_from_text(text or "")
    for u in ent.upi_ids[:3]:
        _lookup(u)
    for p in ent.phones[:3]:
        _lookup(p)

    # De-dup and attach cluster summaries.
    seen: set = set()
    clusters: List[Dict[str, Any]] = []
    g = intel.graph()
    for m in hits:
        for cid in m.get("clusters", []):
            if cid in seen:
                continue
            seen.add(cid)
            cl = next((c for c in g.clusters if c.cluster_id == cid), None)
            if cl:
                clusters.append({
                    "cluster_id": cl.cluster_id,
                    "primary_scam": cl.primary_scam_name,
                    "size": cl.size,
                    "risk": cl.risk,
                    "states": cl.states,
                })
    return {
        "known_infrastructure": bool(clusters),
        "matched_entities": [
            {"kind": m["kind"], "value": m["value"], "case_count": m["case_count"]}
            for m in hits
        ][:5],
        "clusters": clusters,
    }


def verify(
    *,
    text: str = "",
    number: Optional[str] = None,
    upi: Optional[str] = None,
    claimed_identity: Optional[str] = None,
    city: Optional[str] = None,
) -> Dict[str, Any]:
    """Full citizen verification. Fuses Module 1 scoring with Module 2 intel and
    attaches guidance + emergency response."""
    # What are we actually scoring? Prefer the message text; fall back to a bare
    # UPI or "call from <number>" so there is always something for the analyzer.
    artifact = text.strip()
    if not artifact and upi:
        artifact = upi
    if not artifact and number:
        artifact = f"call from {number}"

    analysis = asdict(
        analyze_text(
            artifact or "",
            kind="citizen",
            claimed_identity=claimed_identity,
            caller_number=number,
        )
    )

    intel_ctx = _intel_match(number, upi, artifact)
    extracted = _extract_entities(artifact, number, upi)

    # Peak stage drives the guidance. The analyzer reports stages_seen; pick the
    # most advanced one as the "current stage" for guidance/response.
    stage = _peak_stage(analysis.get("stages_seen", []))
    level = analysis.get("level", "CALM")
    verdict = analysis.get("verdict", "INSUFFICIENT")

    # Module 2 corroboration raises confidence. If the number/UPI is known fraud
    # infrastructure, a merely-SUSPICIOUS verdict is escalated — the network
    # knows something the words alone did not.
    if intel_ctx["known_infrastructure"] and verdict in ("SUSPICIOUS", "INSUFFICIENT"):
        verdict = "LIKELY_SCAM"
        if level in ("CALM", "WATCH", "ELEVATED"):
            level = "HIGH"

    payment_risk = stage in ("PAYMENT_SETUP", "PAYMENT_EXECUTION") or bool(analysis.get("upi"))
    guidance = build_guidance(stage, level)
    response = build_response(level, stage, payment_risk=payment_risk)

    # Nearby hotspots from Module 2, if the citizen shared a city.
    hotspots = _nearby_hotspots(city) if city else []

    return {
        "verdict": verdict,
        "level": level,
        "score": analysis.get("score", 0.0),
        "stage": stage,
        "summary": analysis.get("summary"),
        "analysis": analysis,          # full Module 1 output, for the detail view
        "intel": intel_ctx,            # Module 2 corroboration
        "extracted_entities": extracted,  # what KAVACH pulled out, so the citizen never types it
        "guidance": guidance.as_dict(),
        "emergency": response.as_dict(),
        "nearby_hotspots": hotspots,
        "degraded": analysis.get("degraded", []),
    }


def _extract_entities(text: str, number: Optional[str], upi: Optional[str]) -> Dict[str, List[str]]:
    """Everything KAVACH could pull out of the evidence on its own — so the
    citizen never has to type a number/UPI/email the message already contains.
    Explicitly-provided identifiers are merged in and de-duplicated."""
    from ..intel.entities import extract_from_text

    ent = extract_from_text(text or "")

    def _dedup(values: List[str]) -> List[str]:
        seen: set = set()
        out: List[str] = []
        for v in values:
            if v and v not in seen:
                seen.add(v)
                out.append(v)
        return out

    return {
        "phones": _dedup(([number] if number else []) + list(ent.phones))[:6],
        "upi_ids": _dedup(([upi] if upi else []) + list(ent.upi_ids))[:6],
        "emails": _dedup(list(ent.emails))[:6],
        "websites": _dedup(list(ent.domains))[:6],
        "bank_accounts": _dedup(list(ent.bank_accounts))[:6],
        "banks": _dedup(list(ent.banks))[:6],
        "authorities": _dedup(list(ent.authorities))[:6],
        "locations": _dedup(list(ent.locations))[:6],
        "scam_keywords": _dedup(list(ent.scam_keywords))[:8],
        "amounts": _dedup([str(a) for a in ent.amounts])[:6],
    }


_STAGE_RANK = {
    "GREETING": 0, "AUTHORITY_CLAIM": 1, "FEAR_INDUCTION": 2, "ISOLATION": 3,
    "VERIFICATION_DEMAND": 4, "PAYMENT_SETUP": 5, "PAYMENT_EXECUTION": 6, "BENIGN": -1,
}


def _peak_stage(stages_seen: List[str]) -> str:
    if not stages_seen:
        return "BENIGN"
    return max(stages_seen, key=lambda s: _STAGE_RANK.get(s, -1))


def _nearby_hotspots(city: str) -> List[Dict[str, Any]]:
    from ..intel.geo import CITIES, hotspots

    geo = CITIES.get(city)
    if not geo:
        return []
    state = geo[3]
    g = get_intel().graph()
    all_hot = hotspots([c.as_dict() for c in g.cases])
    # Same-state district and city hotspots — "in your area".
    local = [h for h in all_hot["cities"] if CITIES.get(h["name"], ("", "", "", ""))[3] == state]
    return local[:5]
