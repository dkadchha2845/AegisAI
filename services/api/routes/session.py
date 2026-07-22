"""
Live-session routes: the WebSocket the console renders from, plus REST
equivalents for every action so the UI can be driven without a socket.

The REST duplicates are not redundancy for its own sake. A demo that only
works over a WebSocket has exactly one way to fail in front of an audience,
and `curl`-able actions mean the guardian flow can be rehearsed, scripted, and
recovered from a second browser tab if the socket drops.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import audit
from ..auth import get_current_user
from ..config import settings
from ..db import get_db
from ..engine.report import build_evidence_package
from ..engine.report_pdf import pdf_available, render_pdf
from ..engine.session import registry
from ..models_db import User

router = APIRouter(prefix="/api/session", tags=["session"])


class StartRequest(BaseModel):
    caller_number: Optional[str] = None
    guardian_name: Optional[str] = None


class InjectRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    speaker: str = "CALLER"
    duration_s: float = 3.0
    #: In-flight ASR text. Rendered dimmed, never classified — a half-finished
    #: sentence produces a label that flips as the rest of it arrives.
    partial: bool = False


class PaymentRequest(BaseModel):
    amount_inr: float = Field(gt=0)
    payee: Optional[str] = None


def _require(session_id: str):
    session = registry.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"No session {session_id}")
    return session


@router.post("")
def start_session(req: StartRequest) -> Dict[str, Any]:
    session = registry.create(caller_number=req.caller_number)
    if req.guardian_name:
        session.guardian_name = req.guardian_name
    return session.frame()


@router.get("")
def list_sessions() -> Dict[str, Any]:
    return {
        "sessions": [
            {
                "id": s.id,
                "status": s.status,
                "t": s.t,
                "threat": s.threat_score,
                "level": s.threat_level,
                "stage": s.stage,
                "utterances": len(s.utterances),
            }
            for s in registry.all()
        ]
    }


@router.get("/{session_id}")
def get_frame(session_id: str) -> Dict[str, Any]:
    return _require(session_id).frame()


@router.post("/{session_id}/utterance")
def inject(session_id: str, req: InjectRequest) -> Dict[str, Any]:
    session = _require(session_id)
    if req.partial:
        session.set_partial(req.text, req.speaker)
    else:
        session.ingest(req.text, speaker=req.speaker, duration_s=req.duration_s)
    return {"frame": session.frame(), "events": session.drain_events()}


@router.post("/{session_id}/guardian/ack")
def guardian_ack(session_id: str, name: Optional[str] = None) -> Dict[str, Any]:
    session = _require(session_id)
    session.guardian_ack(name)
    return {"frame": session.frame(), "events": session.drain_events()}


@router.post("/{session_id}/payment/attempt")
def attempt_payment(
    session_id: str,
    req: PaymentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    session = _require(session_id)
    outcome = session.attempt_payment(req.amount_inr, req.payee)
    audit.record(
        db, "payment.attempt", actor=user.email, target=session_id,
        detail=f"₹{req.amount_inr:.0f} -> {outcome.get('state')}"
               + (f" ({outcome.get('reason')})" if outcome.get("reason") else ""),
    )
    return {"outcome": outcome, "frame": session.frame(), "events": session.drain_events()}


@router.post("/{session_id}/payment/cancel")
def cancel_payment(
    session_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    session = _require(session_id)
    session.cancel_payment()
    audit.record(db, "payment.cancel", actor=user.email, target=session_id)
    return {"frame": session.frame(), "events": session.drain_events()}


@router.post("/{session_id}/payment/approve")
def approve_payment(
    session_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    session = _require(session_id)
    session.approve_payment()
    # The override — the single most consequential action in the product. It
    # always leaves a trace: who released a hold the system had flagged.
    audit.record(
        db, "payment.override", actor=user.email, target=session_id,
        detail=f"released hold at threat {session.threat_score:.0f}/100",
    )
    return {"frame": session.frame(), "events": session.drain_events()}


@router.get("/{session_id}/report")
def evidence_report(session_id: str) -> Dict[str, Any]:
    """The structured, MHA/cybercrime-compatible evidence package.

    Machine-readable and self-describing: the verdict, the named signals behind
    it, the identity and caller-number evidence with citations, the manipulation
    timeline, the full transcript, and reporting guidance. This is the artifact
    that turns an in-app alert into something a telecom provider or cybercrime
    cell can act on and file.
    """
    session = _require(session_id)
    return build_evidence_package(session)


@router.post("/{session_id}/investigate")
def investigate_session(session_id: str, city: Optional[str] = None) -> Dict[str, Any]:
    """Turn a live call into the same fused citizen report the Analyze page
    produces — Module 1 (verdict) + Module 2 (fraud network / hotspots) +
    Module 3 (guidance / complaint). This is what the citizen Live Protection
    screen shows the moment the call ends: one investigation, two entry points.

    The session's own transcript, caller number, and claimed identity are run
    back through `shield.verify` so the live journey and the upload journey end
    in a byte-identical report.
    """
    session = _require(session_id)
    from ..shield import verify

    transcript = "\n".join(f"{u.speaker}: {u.text}" for u in session.utterances)
    return verify(
        text=transcript,
        number=session.caller_number,
        claimed_identity=session.passport.claimed_identity,
        city=city,
    )


@router.get("/{session_id}/report.pdf")
def evidence_report_pdf(session_id: str) -> Response:
    """The same evidence package rendered as a court-admissible PDF.

    Degrades honestly: if reportlab is not installed the JSON endpoint still
    works and this returns a 503 that says what to do, rather than a stack
    trace or a silent empty file.
    """
    session = _require(session_id)
    if not pdf_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "PDF rendering is unavailable — reportlab is not installed. "
                "Install it (`pip install reportlab`) or use GET "
                f"/api/session/{session_id}/report for the JSON package."
            ),
        )
    package = build_evidence_package(session)
    pdf = render_pdf(package)
    filename = f"{package['report_id']}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{session_id}")
def end_session(session_id: str) -> Dict[str, Any]:
    session = _require(session_id)
    session.end()
    frame = session.frame()
    events = session.drain_events()
    return {"frame": frame, "events": events}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


@router.websocket("/ws/{session_id}")
async def session_socket(websocket: WebSocket, session_id: str) -> None:
    """Push frames on a fixed clock; accept `ClientCommand`s on the same socket.

    Frames go out on a timer rather than on change, because the contract's
    whole premise is that a frame is a snapshot: a client that connects
    mid-call, or misses ten frames, is fully correct after the next tick. Only
    events are change-driven, and they are drained alongside each frame so
    ordering between the two is never ambiguous.
    """
    await websocket.accept()
    session = registry.get(session_id)
    if session is None:
        await websocket.send_json(
            {
                "v": 1, "type": "error", "session_id": session_id,
                "code": "no_such_session",
                "message": f"No session {session_id}. POST /api/session first.",
                "recoverable": False,
            }
        )
        await websocket.close()
        return

    interval = 1.0 / max(settings.frame_hz, 0.5)

    async def pump() -> None:
        while True:
            for event in session.drain_events():
                await websocket.send_json(event)
            await websocket.send_json(session.frame())
            await asyncio.sleep(interval)

    pump_task = asyncio.create_task(pump())
    try:
        while True:
            message = await websocket.receive_json()
            action = message.get("action")
            payload = message.get("payload") or {}

            if action == "inject_text":
                if payload.get("partial"):
                    session.set_partial(payload.get("text", ""), payload.get("speaker", "CALLER"))
                else:
                    session.ingest(
                        payload.get("text", ""),
                        speaker=payload.get("speaker", "CALLER"),
                        duration_s=float(payload.get("duration_s", 3.0)),
                    )
            elif action == "guardian_ack":
                session.guardian_ack(payload.get("name"))
            elif action == "attempt_payment":
                session.attempt_payment(
                    float(payload.get("amount_inr", 0) or 0), payload.get("payee")
                )
            elif action == "guardian_cancel_payment":
                session.cancel_payment()
            elif action == "guardian_approve_payment":
                session.approve_payment()
            elif action == "end_session":
                session.end()
            else:
                await websocket.send_json(
                    {
                        "v": 1, "type": "error", "session_id": session_id,
                        "code": "unknown_action",
                        "message": f"Unsupported action {action!r}.",
                        "recoverable": True,
                    }
                )
    except WebSocketDisconnect:
        pass
    finally:
        pump_task.cancel()
