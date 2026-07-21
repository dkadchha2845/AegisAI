"""
Case book — saved evidence packages and the audit log.

Saving a report is the point at which a live, ephemeral session becomes a
durable case file: the package is persisted verbatim and the export is written
to the audit log, so "who escalated this call, and when" has an answer that
survives the process. Listing and reading are viewer-level; saving is an
analyst action; the audit log is admin-only.

With the default in-memory database these live for the process like everything
else; point DATABASE_URL at a file or Postgres and they persist for real.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import audit
from ..auth import get_current_user, require_role
from ..db import get_db
from ..engine.report import build_evidence_package
from ..engine.session import registry
from ..models_db import CaseRecord, User

router = APIRouter(tags=["reports"])


@router.post("/api/session/{session_id}/report/save", status_code=201)
def save_report(
    session_id: str,
    user: User = Depends(require_role("analyst")),
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
    )
    return {"record": record.as_summary(), "package": package}


@router.get("/api/reports")
def list_reports(
    _: User = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
) -> Dict[str, List[Dict[str, Any]]]:
    records = db.query(CaseRecord).order_by(CaseRecord.created_at.desc()).limit(200).all()
    return {"reports": [r.as_summary() for r in records]}


@router.get("/api/reports/{report_id}")
def get_report(
    report_id: str,
    _: User = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    record = db.query(CaseRecord).filter(CaseRecord.report_id == report_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail=f"No saved report {report_id}")
    return {"record": record.as_summary(), "package": json.loads(record.package_json)}


@router.get("/api/audit")
def audit_log(
    action: Optional[str] = None,
    limit: int = 200,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> Dict[str, List[Dict[str, Any]]]:
    events = audit.recent(db, limit=min(limit, 500), action=action)
    return {"events": [e.as_public() for e in events]}
