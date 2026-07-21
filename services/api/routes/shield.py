"""
CFSRP routes (Module 3) — the citizen-facing surface.

Unlike the investigator and platform routes, these are **public**: a citizen in
the middle of a scam has no account and no time to make one. Verification, guided
guidance, and the emergency directory need no auth. Preserving evidence returns
an unguessable token; reading the vault or generating the complaint requires
holding that token — object-level access by possession, since there is no user
to scope by. Nothing here exposes another citizen's report, and nothing accepts
executable uploads.

Everything is rate-limited at the middleware layer (see `security.py`) so the
public surface cannot be used to hammer the analyzer.
"""

from __future__ import annotations

import secrets
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..engine.report_pdf import pdf_available, render_pdf
from ..models_db import CitizenReport
from ..shield import build_complaint, verify
from ..shield.complaint import complaint_to_evidence_package
from ..shield.response import HELPLINES

router = APIRouter(prefix="/api/shield", tags=["shield"])


class VerifyRequest(BaseModel):
    text: str = Field(default="", max_length=20_000)
    number: Optional[str] = Field(default=None, max_length=32)
    upi: Optional[str] = Field(default=None, max_length=128)
    claimed_identity: Optional[str] = Field(default=None, max_length=200)
    city: Optional[str] = Field(default=None, max_length=80)
    channel: str = Field(default="web", max_length=24)


class PreserveRequest(VerifyRequest):
    """Verify and preserve in one call — what the citizen dashboard posts when
    the user taps 'save this as evidence'."""


@router.get("/helplines")
def helplines() -> Dict[str, Any]:
    """The official reporting directory. Public and static — the one thing a
    citizen must always be able to reach, even if everything else is down."""
    return {"helplines": HELPLINES}


@router.post("/verify")
def verify_route(req: VerifyRequest) -> Dict[str, Any]:
    """Verify a suspicious message / number / UPI. Fuses Module 1 + Module 2 and
    returns the verdict, stage-aware guidance, and an emergency response."""
    if not (req.text.strip() or req.number or req.upi):
        raise HTTPException(
            status_code=422,
            detail="Provide a message, a caller number, or a UPI ID to check.",
        )
    return verify(
        text=req.text,
        number=req.number,
        upi=req.upi,
        claimed_identity=req.claimed_identity,
        city=req.city,
    )


@router.post("/preserve", status_code=201)
def preserve_route(req: PreserveRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Verify and preserve the submission in the evidence vault. Returns a token
    the citizen keeps to retrieve the report or generate a complaint later."""
    result = verify(
        text=req.text, number=req.number, upi=req.upi,
        claimed_identity=req.claimed_identity, city=req.city,
    )
    import json

    token = secrets.token_urlsafe(24)
    record = CitizenReport(
        token=token,
        channel=req.channel,
        city=req.city,
        caller_number=req.number,
        upi_id=req.upi,
        verdict=result.get("verdict"),
        level=result.get("level"),
        score=result.get("score"),
        scam_stage=result.get("stage"),
        result_json=json.dumps({"result": result, "submitted_text": req.text},
                               ensure_ascii=False),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # Feed the citizen report into Module 2 as well — a citizen submission is a
    # detection too, and should grow the fraud graph. Best-effort.
    try:
        from ..intel import get_intel
        from ..shield.complaint import build_complaint as _bc

        complaint = _bc(result, submitted_text=req.text, channel=req.channel, city=req.city)
        get_intel().ingest_package(complaint_to_evidence_package(complaint), city=req.city)
    except Exception:  # noqa: BLE001
        pass

    return {"token": token, "summary": record.as_summary(), "result": result}


@router.get("/vault/{token}")
def vault_read(token: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Read a preserved report by its token. Possession of the token is the
    authorization — there is no citizen account to scope by."""
    import json

    record = _require_report(db, token)
    blob = json.loads(record.result_json)
    return {"summary": record.as_summary(), **blob}


@router.get("/vault/{token}/complaint")
def vault_complaint(token: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Generate the structured cybercrime-complaint package for a preserved
    report."""
    import json

    record = _require_report(db, token)
    blob = json.loads(record.result_json)
    complaint = build_complaint(
        blob.get("result", {}),
        submitted_text=blob.get("submitted_text", ""),
        channel=record.channel,
        city=record.city,
    )
    return complaint


@router.get("/vault/{token}/complaint.pdf")
def vault_complaint_pdf(token: str, db: Session = Depends(get_db)) -> Response:
    """The complaint as a PDF, rendered by the same engine as the Module 1
    evidence package. 503 if reportlab is absent, with the JSON route as the
    fallback."""
    import json

    record = _require_report(db, token)
    if not pdf_available():
        raise HTTPException(
            status_code=503,
            detail="PDF rendering is unavailable — reportlab is not installed. "
                   f"Use GET /api/shield/vault/{token}/complaint for the JSON package.",
        )
    blob = json.loads(record.result_json)
    complaint = build_complaint(
        blob.get("result", {}), submitted_text=blob.get("submitted_text", ""),
        channel=record.channel, city=record.city,
    )
    pdf = render_pdf(complaint_to_evidence_package(complaint))
    filename = f"{complaint['complaint_id']}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/awareness")
def awareness(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Fraud-awareness feed: the scam types and hotspots the network is seeing
    most right now (from Module 2), so a citizen learns what is circulating in
    their area. Public and read-only."""
    from ..intel import get_intel

    g = get_intel().graph()
    top_clusters = [
        {
            "cluster_id": c.cluster_id,
            "scam": c.primary_scam_name,
            "size": c.size,
            "risk": c.risk,
            "states": c.states,
        }
        for c in g.clusters[:5]
    ]
    from ..intel.geo import hotspots

    hs = hotspots([c.as_dict() for c in g.cases])
    return {
        "trending_scams": top_clusters,
        "hotspot_states": hs["states"][:6],
    }


def _require_report(db: Session, token: str) -> CitizenReport:
    record = db.query(CitizenReport).filter(CitizenReport.token == token).first()
    if record is None:
        raise HTTPException(status_code=404, detail="No preserved report for that token.")
    return record
