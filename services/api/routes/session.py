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

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import audit
from .. import auth as auth_mod
from ..auth import public, require_permission, user_if_any
from ..config import settings
from ..db import get_db
from ..engine.report import build_evidence_package
from ..engine.report_pdf import pdf_available, render_pdf
from ..engine.session import Session as LiveSession
from ..engine.session import issue_token, registry, token_matches
from ..models_db import User
from ..permissions import permissions_for

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


# --- who may touch a session (audit S-07) -----------------------------------
#
# A live session holds a person's call: what the caller said, what the victim
# said, the caller's number, and the controls that hold or release a payment.
# Its id travels in every URL and every frame, so the id is not a secret. Until
# S-07 it was the only thing any of these routes asked for.
#
# Now a session is reachable by exactly three parties:
#   1. whoever holds its token — minted when it is created, returned once, and
#      kept only as a hash (`engine/session.issue_token`);
#   2. the signed-in user who created it;
#   3. staff who may read every case in the organisation — the analyst console.
# Anyone else is told the session does not exist: a 404, not a 403, because a
# row you may not read must not be confirmed to exist (docs/AUTH.md).
#
# The token rides in an `X-Session-Token` header, or in `?token=` for the two
# things a browser cannot attach a header to: the WebSocket and a download link.

#: Staff who may watch any live session.
MONITOR_PERMISSION = "INVESTIGATION_READ_ALL"


def _may_access(session: LiveSession, token: Optional[str], user: Optional[User]) -> bool:
    if token_matches(session, token):
        return True
    if user is None:
        return False
    if session.owner_id is not None and user.id == session.owner_id:
        return True
    return MONITOR_PERMISSION in permissions_for(user.role)


def session_access(
    session_id: str,
    x_session_token: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
    user: Optional[User] = Depends(user_if_any),
) -> LiveSession:
    session = registry.get(session_id)
    if session is None or not _may_access(session, x_session_token or token, user):
        raise HTTPException(status_code=404, detail=f"No session {session_id}")
    return session


session_access.aegis_guard = (  # type: ignore[attr-defined]
    "capability",
    f"the session's token, its creator, or {MONITOR_PERMISSION}",
)


@router.post(
    "",
    dependencies=[Depends(public("a citizen starts call protection without an account"))],
)
def start_session(
    req: StartRequest, user: Optional[User] = Depends(user_if_any)
) -> Dict[str, Any]:
    """Open a session. The response is the first frame plus `session_token`,
    which every later call must present — it is not shown again."""
    session = registry.create(caller_number=req.caller_number)
    session.owner_id = user.id if user is not None else None
    if req.guardian_name:
        session.guardian_name = req.guardian_name
    return {**session.frame(), "session_token": issue_token(session)}


@router.get("")
def list_sessions(
    _: User = Depends(require_permission(MONITOR_PERMISSION)),
) -> Dict[str, Any]:
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
def get_frame(session: LiveSession = Depends(session_access)) -> Dict[str, Any]:
    return session.frame()


@router.post("/{session_id}/utterance")
def inject(req: InjectRequest, session: LiveSession = Depends(session_access)) -> Dict[str, Any]:
    if req.partial:
        session.set_partial(req.text, req.speaker)
    else:
        session.ingest(req.text, speaker=req.speaker, duration_s=req.duration_s)
    return {"frame": session.frame(), "events": session.drain_events()}


@router.post("/{session_id}/guardian/ack")
def guardian_ack(
    name: Optional[str] = None, session: LiveSession = Depends(session_access)
) -> Dict[str, Any]:
    session.guardian_ack(name)
    return {"frame": session.frame(), "events": session.drain_events()}


@router.post("/{session_id}/payment/attempt")
def attempt_payment(
    session_id: str,
    req: PaymentRequest,
    user: User = Depends(require_permission("LIVE_SESSION_USE")),
    db: Session = Depends(get_db),
    session: LiveSession = Depends(session_access),
) -> Dict[str, Any]:
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
    user: User = Depends(require_permission("LIVE_SESSION_USE")),
    db: Session = Depends(get_db),
    session: LiveSession = Depends(session_access),
) -> Dict[str, Any]:
    session.cancel_payment()
    audit.record(db, "payment.cancel", actor=user.email, target=session_id)
    return {"frame": session.frame(), "events": session.drain_events()}


@router.post("/{session_id}/payment/approve")
def approve_payment(
    session_id: str,
    user: User = Depends(require_permission("LIVE_SESSION_USE")),
    db: Session = Depends(get_db),
    session: LiveSession = Depends(session_access),
) -> Dict[str, Any]:
    session.approve_payment()
    # The override — the single most consequential action in the product. It
    # always leaves a trace: who released a hold the system had flagged.
    audit.record(
        db, "payment.override", actor=user.email, target=session_id,
        detail=f"released hold at threat {session.threat_score:.0f}/100",
    )
    return {"frame": session.frame(), "events": session.drain_events()}


@router.get("/{session_id}/report")
def evidence_report(session: LiveSession = Depends(session_access)) -> Dict[str, Any]:
    """The structured, MHA/cybercrime-compatible evidence package.

    Machine-readable and self-describing: the verdict, the named signals behind
    it, the identity and caller-number evidence with citations, the manipulation
    timeline, the full transcript, and reporting guidance. This is the artifact
    that turns an in-app alert into something a telecom provider or cybercrime
    cell can act on and file.
    """
    return build_evidence_package(session)


@router.post("/{session_id}/investigate")
def investigate_session(
    city: Optional[str] = None, session: LiveSession = Depends(session_access)
) -> Dict[str, Any]:
    """Turn a live call into the same fused citizen report the Analyze page
    produces — Module 1 (verdict) + Module 2 (fraud network / hotspots) +
    Module 3 (guidance / complaint). This is what the citizen Live Protection
    screen shows the moment the call ends: one investigation, two entry points.

    The session's own transcript, caller number, and claimed identity are run
    back through `shield.verify` so the live journey and the upload journey end
    in a byte-identical report.
    """
    from ..shield import verify

    transcript = "\n".join(f"{u.speaker}: {u.text}" for u in session.utterances)
    return verify(
        text=transcript,
        number=session.caller_number,
        claimed_identity=session.passport.claimed_identity,
        city=city,
    )


@router.get("/{session_id}/report.pdf")
def evidence_report_pdf(session: LiveSession = Depends(session_access)) -> Response:
    """The same evidence package rendered as a court-admissible PDF.

    Degrades honestly: if reportlab is not installed the JSON endpoint still
    works and this returns a 503 that says what to do, rather than a stack
    trace or a silent empty file.
    """
    if not pdf_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "PDF rendering is unavailable — reportlab is not installed. "
                "Install it (`pip install reportlab`) or use GET "
                f"/api/session/{session.id}/report for the JSON package."
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
def end_session(session: LiveSession = Depends(session_access)) -> Dict[str, Any]:
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
    # A socket cannot carry a header, so the token comes as `?token=`. Open demo
    # mode lets an anonymous socket through, exactly as it does every REST call.
    # A refused socket is told the session does not exist, as REST is.
    if session is not None and not (
        token_matches(session, websocket.query_params.get("token")) or not auth_mod.auth_enabled()
    ):
        session = None
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
            elif action in ("attempt_payment", "guardian_cancel_payment",
                            "guardian_approve_payment"):
                # Holding and releasing money is permission-checked and audited
                # over REST (`LIVE_SESSION_USE`, an audit row naming who did it).
                # The socket used to accept the same actions from anyone holding
                # it, with neither check — releasing a flagged payment hold left
                # no trace (S-07). It now points at the audited route.
                await websocket.send_json(
                    {
                        "v": 1, "type": "error", "session_id": session_id,
                        "code": "use_rest",
                        "message": (
                            f"{action} is not accepted over the socket. Use "
                            f"POST /api/session/{session_id}/payment/... — it is "
                            "permission-checked and audited."
                        ),
                        "recoverable": True,
                    }
                )
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


session_socket.aegis_guard = (  # type: ignore[attr-defined]
    "capability",
    "the session's token as ?token=, or open demo mode",
)
