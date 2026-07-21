"""
Auth routes — login, whoami, and (admin-only) user management.

Single-org RBAC: there is one organisation, and the three roles form a ladder
(viewer < analyst < admin). Login is intentionally uniform — a wrong email and a
wrong password return the same 401, so the endpoint is not an account-existence
oracle.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
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


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
    user = get_user_by_email(db, req.email)
    # Same error whether the email is unknown or the password is wrong, and the
    # password is still verified against a real hash on the miss path so timing
    # does not distinguish the two.
    dummy = "pbkdf2_sha256$240000$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    ok = verify_password(req.password, user.password_hash if user else dummy)
    if not user or user.disabled or not ok:
        audit.record(db, "login.failed", actor=req.email,
                     detail="invalid email or password")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    audit.record(db, "login", actor=user.email)
    return {"token": create_token(user), "user": user.as_public()}


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """The current identity. In open mode this is the seeded admin, so the UI
    can render a consistent 'signed in as' without special-casing the flag."""
    return {"user": user.as_public(), "auth_enforced": auth_enabled()}


@router.get("/users")
def list_users(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> Dict[str, List[Dict[str, Any]]]:
    users = db.query(User).order_by(User.id.asc()).all()
    return {"users": [u.as_public() for u in users]}


@router.post("/users", status_code=201)
def add_user(
    req: NewUserRequest,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    if req.role not in ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {ROLES}")
    if get_user_by_email(db, req.email):
        raise HTTPException(status_code=409, detail="A user with that email already exists")
    user = create_user(db, req.email, req.password, role=req.role)
    audit.record(db, "user.create", actor=admin.email, target=user.email,
                 detail=f"role={user.role}")
    return {"user": user.as_public()}
