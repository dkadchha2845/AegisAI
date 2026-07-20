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

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ..config import settings
from ..engine.session import registry

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
def attempt_payment(session_id: str, req: PaymentRequest) -> Dict[str, Any]:
    session = _require(session_id)
    outcome = session.attempt_payment(req.amount_inr, req.payee)
    return {"outcome": outcome, "frame": session.frame(), "events": session.drain_events()}


@router.post("/{session_id}/payment/cancel")
def cancel_payment(session_id: str) -> Dict[str, Any]:
    session = _require(session_id)
    session.cancel_payment()
    return {"frame": session.frame(), "events": session.drain_events()}


@router.post("/{session_id}/payment/approve")
def approve_payment(session_id: str) -> Dict[str, Any]:
    session = _require(session_id)
    session.approve_payment()
    return {"frame": session.frame(), "events": session.drain_events()}


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
