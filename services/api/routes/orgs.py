"""
Organisation management (multi-tenant Track 2 extension).

Owner-only, except `current` which any signed-in user can read to know which
tenant they are in. Creating an org and listing all orgs are platform-superadmin
actions; an org admin manages users *within* their org through the auth routes,
not here. Single-org installs simply never call these — the default org is
seeded and everyone is already in it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import audit
from ..auth import get_current_user, require_role
from ..db import get_db
from ..models_db import CaseRecord, Organization, User
from ..orgs import create_org, get_org

router = APIRouter(prefix="/api/orgs", tags=["orgs"])


class NewOrgRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: Optional[str] = Field(default=None, max_length=64)


@router.get("")
def list_orgs(
    _: User = Depends(require_role("owner")),
    db: Session = Depends(get_db),
) -> Dict[str, List[Dict[str, Any]]]:
    """Every organisation, with a member and case count — the platform view."""
    orgs = db.query(Organization).order_by(Organization.id.asc()).all()
    out = []
    for org in orgs:
        members = db.query(User).filter(User.org_id == org.id).count()
        cases = db.query(CaseRecord).filter(CaseRecord.org_id == org.id).count()
        out.append({**org.as_public(), "members": members, "cases": cases})
    return {"organizations": out}


@router.post("", status_code=201)
def new_org(
    req: NewOrgRequest,
    owner: User = Depends(require_role("owner")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Create a tenant. Owner-only."""
    org = create_org(db, req.name, slug=req.slug)
    audit.record(db, "org.create", actor=owner.email, target=org.slug,
                 detail=f"name={org.name}", org_id=owner.org_id)
    return {"organization": org.as_public()}


@router.get("/current")
def current_org(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """The tenant the current user belongs to (null for a platform owner with no
    org). Any signed-in user may read this."""
    org = get_org(db, user.org_id)
    return {"organization": org.as_public() if org else None, "is_owner": user.role == "owner"}
