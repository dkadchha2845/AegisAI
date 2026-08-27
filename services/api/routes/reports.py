"""
Case book — saved evidence packages and the audit log.

Saving a report is the point at which a live, ephemeral session becomes a
durable case file: the package is persisted verbatim and the export is written
to the audit log, so "who escalated this call, and when" has an answer that
survives the process.

**Two scopes, not one.** `REPORT_READ_ALL` sees every case file in the
organisation — that is what an analyst, an investigator and an administrator
have always had. A citizen holds only `REPORT_READ_OWN`, and `_visible()` below
narrows their query to the rows they created. The narrowing happens in the
query, never in a post-filter over rows already loaded: filtering after the fact
is how an off-by-one in a template leaks the row it should not have fetched.

A case id that belongs to someone else 404s rather than 403s, so a report id
cannot be probed for existence from outside the scope that owns it.

With the default in-memory database these live for the process like everything
else; point DATABASE_URL at a file or Postgres and they persist for real.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import audit
from ..auth import require_permission, user_permissions
from ..db import get_db
from ..engine.report import build_evidence_package
from ..engine.session import registry
from ..models_db import CaseRecord, User
from ..orgs import scope_query

router = APIRouter(tags=["reports"])


@router.post("/api/session/{session_id}/report/save", status_code=201)
def save_report(
    session_id: str,
    user: User = Depends(require_permission("REPORT_CREATE")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Build the evidence package and persist it as a case record."""
    session = registry.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"No session {session_id}")

    package = build_evidence_package(session)
    incident = package.get("incident", {})
    record = CaseRecord(
        report_id=package["report_id"],
        session_id=session_id,
        org_id=user.org_id,
        created_by=user.email,
        caller_number=package.get("call", {}).get("caller_number"),
        incident_type=incident.get("type"),
        peak_threat=incident.get("peak_threat"),
        final_level=incident.get("final_level"),
        package_json=json.dumps(package, ensure_ascii=False),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    audit.record(
        db, "report.export", actor=user.email, target=package["report_id"],
        detail=f"saved case for session {session_id} "
               f"(peak {incident.get('peak_threat')}/100)",
        org_id=user.org_id,
    )

    # Feed the detection into Module 2 (FIGAE): the saved evidence package becomes
    # a node in the fraud graph, so a call detected now appears in the network and
    # its hotspots immediately. This is the PDF's "Source 2 — real-time
    # intelligence from Module 1" wired end to end. Best-effort: a graph rebuild
    # failure must not fail the save that already committed.
    try:
        from ..intel import get_intel

        get_intel().ingest_package(package)
    except Exception:
        pass

    return {"record": record.as_summary(), "package": package}


def _visible(db: Session, user: User):
    """The case-record query this user is allowed to run.

    Two narrowings, applied in order. `scope_query` restricts to the user's
    organisation (an owner is platform-wide). Then, unless they hold
    `REPORT_READ_ALL`, the rows are narrowed again to the ones they created —
    which is what makes "a citizen sees only their own reports" a property of
    the SQL rather than of the page that renders it.
    """
    q = scope_query(db.query(CaseRecord), CaseRecord, user)
    if "REPORT_READ_ALL" not in user_permissions(user):
        q = q.filter(CaseRecord.created_by == user.email)
    return q


@router.get("/api/reports")
def list_reports(
    user: User = Depends(require_permission("REPORT_READ_OWN")),
    db: Session = Depends(get_db),
) -> Dict[str, List[Dict[str, Any]]]:
    records = _visible(db, user).order_by(CaseRecord.created_at.desc()).limit(200).all()
    return {"reports": [r.as_summary() for r in records]}


@router.get("/api/reports/{report_id}")
def get_report(
    report_id: str,
    user: User = Depends(require_permission("REPORT_READ_OWN")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    # Object-level scoping too — a report id from another org, or another
    # person's report where the caller may only read their own, 404s rather
    # than leaking. That is the IDOR the audit called out, now closed against
    # a second reader as well as a second tenant.
    record = _visible(db, user).filter(CaseRecord.report_id == report_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail=f"No saved report {report_id}")
    return {"record": record.as_summary(), "package": json.loads(record.package_json)}


@router.get("/api/audit")
def audit_log(
    action: Optional[str] = None,
    limit: int = 200,
    user: User = Depends(require_permission("AUDIT_READ")),
    db: Session = Depends(get_db),
) -> Dict[str, List[Dict[str, Any]]]:
    from ..models_db import AuditEvent

    q = scope_query(db.query(AuditEvent), AuditEvent, user)
    if action:
        q = q.filter(AuditEvent.action == action)
    events = q.order_by(AuditEvent.ts.desc(), AuditEvent.id.desc()).limit(min(limit, 500)).all()
    return {"events": [e.as_public() for e in events]}
