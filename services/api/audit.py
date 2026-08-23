"""
Audit log — append-only, best-effort.

`record()` never raises: an audit write failing must not break the action it was
recording (a payment hold must still hold even if the log is unavailable), so a
failure is swallowed after rolling back. That is the right trade-off for a log
whose purpose is *additional* accountability, not a transactional guarantee — if
you need the stronger guarantee, that is a database with a durable URL, not a
change here.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from .models_db import AuditEvent


def record(
    db: Session,
    action: str,
    *,
    actor: Optional[str] = None,
    target: Optional[str] = None,
    detail: Optional[str] = None,
    org_id: Optional[int] = None,
) -> None:
    """Append one event. Best-effort — swallows its own errors."""
    try:
        db.add(AuditEvent(actor=actor or "anonymous", action=action,
                          target=target, detail=detail, org_id=org_id))
        db.commit()
    except Exception:
        db.rollback()


def recent(db: Session, limit: int = 200, action: Optional[str] = None) -> List[AuditEvent]:
    q = db.query(AuditEvent)
    if action:
        q = q.filter(AuditEvent.action == action)
    return q.order_by(AuditEvent.ts.desc(), AuditEvent.id.desc()).limit(limit).all()
