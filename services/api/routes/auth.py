"""
Auth routes — login, whoami, and (admin-only) user management.

Single-org RBAC: there is one organisation, and the three roles form a ladder
(viewer < analyst < admin). Login is intentionally uniform — a wrong email and a
wrong password return the same 401, so the endpoint is not an account-existence
oracle.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import audit
from ..auth import (
    auth_enabled,
    create_token,
    create_user,
    get_current_user,
    get_user_by_email,
    require_role,
    verify_password,
)
from ..db import get_db
from ..models_db import ROLES, User
from ..orgs import scope_query
from ..security import login_locked, record_login_attempt

router = APIRouter(prefix="/api/auth", tags=["auth"])


# A light email shape check — full RFC validation would need email-validator,
# a dependency this project does not carry. The pattern rejects the obvious
# nonsense; correctness of the address is proven by the account existing.
_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=_EMAIL)
    password: str = Field(min_length=1, max_length=256)


class NewUserRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=_EMAIL)
    password: str = Field(min_length=8, max_length=256)
    role: str = "viewer"
    #: An owner may place the new user in a specific org; ignored for org admins,
    #: who can only add to their own.
    org_id: Optional[int] = None


@router.post("/login")
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ip = request.client.host if request.client else "unknown"

    # Backoff (CWE-307): after repeated failures for this email+IP, refuse for a
    # cooling-off window rather than letting a script keep guessing.
    locked = login_locked(req.email, ip)
    if locked > 0:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {int(locked)}s.",
            headers={"Retry-After": str(int(locked))},
        )

    user = get_user_by_email(db, req.email)
    # Same error whether the email is unknown or the password is wrong, and the
    # password is still verified against a real hash on the miss path so timing
    # does not distinguish the two.
    dummy = "pbkdf2_sha256$240000$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    ok = verify_password(req.password, user.password_hash if user else dummy)
    if not user or user.disabled or not ok:
        record_login_attempt(req.email, ip, success=False)
        audit.record(db, "login.failed", actor=req.email,
                     detail="invalid email or password")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    record_login_attempt(req.email, ip, success=True)
    audit.record(db, "login", actor=user.email)
    return {"token": create_token(user), "user": user.as_public()}


@router.get("/me")
def me(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """The current identity and tenant. In open mode this is the seeded owner, so
    the UI can render a consistent 'signed in as' without special-casing the flag."""
    from ..orgs import get_org

    org = get_org(db, user.org_id)
    return {
        "user": user.as_public(),
        "org": org.as_public() if org else None,
        "auth_enforced": auth_enabled(),
    }


@router.get("/users")
def list_users(
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> Dict[str, List[Dict[str, Any]]]:
    # An org admin manages only their own org's users; an owner sees everyone.
    q = scope_query(db.query(User), User, admin)
    users = q.order_by(User.id.asc()).all()
    return {"users": [u.as_public() for u in users]}


@router.post("/users", status_code=201)
def add_user(
    req: NewUserRequest,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    if req.role not in ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {ROLES}")
    # Only an owner may mint another owner; an org admin cannot escalate past
    # their own ceiling or create a platform superadmin.
    if req.role == "owner" and admin.role != "owner":
        raise HTTPException(status_code=403, detail="Only a platform owner can create an owner.")
    if get_user_by_email(db, req.email):
        raise HTTPException(status_code=409, detail="A user with that email already exists")
    # New users join the creating admin's org (an owner can pass an explicit org).
    target_org = req.org_id if (admin.role == "owner" and req.org_id is not None) else admin.org_id
    user = create_user(db, req.email, req.password, role=req.role, org_id=target_org)
    audit.record(db, "user.create", actor=admin.email, target=user.email,
                 detail=f"role={user.role} org={target_org}", org_id=admin.org_id)
    return {"user": user.as_public()}
