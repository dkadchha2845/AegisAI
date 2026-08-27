"""
Audit log — append-only, best-effort.

`record()` never raises: an audit write failing must not break the action it was
recording (a payment hold must still hold even if the log is unavailable), so a
failure is swallowed after rolling back. That is the right trade-off for a log
whose purpose is *additional* accountability, not a transactional guarantee — if
you need the stronger guarantee, that is a database with a durable URL, not a
change here.

**Nothing secret is ever written.** No password, no token, no reset token, no
password hash. This module is the only writer of `audit_events`, which is what
makes that rule checkable in one place instead of at fifty call sites.

`from_request()` exists so a route can attach the caller's IP and user agent
without every route re-deriving them, and so the truncation of that
attacker-controlled free text happens once.
"""

from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy.orm import Session

from .models_db import AuditEvent

#: Longest user-agent string stored. A user agent is attacker-controlled and
#: unbounded; the column is 256 and this is where it is made to fit.
_UA_MAX = 256


def from_request(request: Any) -> dict:
    """`{"ip": …, "user_agent": …}` for a Starlette/FastAPI request, or empty.

    Takes `Any` and tolerates `None` because several call sites are reachable
    from both a route (which has a request) and a background task (which does
    not), and an audit helper that raises when handed the wrong thing defeats
    the point of a best-effort log.
    """
    if request is None:
        return {}
    try:
        client = getattr(request, "client", None)
        ua = request.headers.get("user-agent") if hasattr(request, "headers") else None
    except Exception:  # pragma: no cover - defensive; a log helper never raises
        return {}
    return {
        "ip": getattr(client, "host", None) if client else None,
        "user_agent": (ua or "")[:_UA_MAX] or None,
    }


def record(
    db: Session,
    action: str,
    *,
    actor: Optional[str] = None,
    actor_user_id: Optional[int] = None,
    target: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    success: bool = True,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    detail: Optional[str] = None,
    org_id: Optional[int] = None,
) -> None:
    """Append one event. Best-effort — swallows its own errors.

    Every argument past `action` is optional and every one of them was optional
    before, which is what keeps the ~20 existing call sites working unchanged.
    """
    try:
        db.add(
            AuditEvent(
                actor=actor or "anonymous",
                actor_user_id=actor_user_id,
                action=action,
                target=target,
                resource_type=resource_type,
                resource_id=resource_id,
                success=success,
                ip=ip,
                user_agent=(user_agent or "")[:_UA_MAX] or None,
                detail=detail,
                org_id=org_id,
            )
        )
        db.commit()
    except Exception:
        db.rollback()


def recent(db: Session, limit: int = 200, action: Optional[str] = None) -> List[AuditEvent]:
    q = db.query(AuditEvent)
    if action:
        q = q.filter(AuditEvent.action == action)
    return q.order_by(AuditEvent.ts.desc(), AuditEvent.id.desc()).limit(limit).all()
