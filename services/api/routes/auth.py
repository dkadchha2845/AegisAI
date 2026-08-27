"""
Auth routes — sign-up, sign-in, session, profile, passwords, and user admin.

    POST   /api/auth/signup            create a CITIZEN account and sign in
    POST   /api/auth/login             email + password -> token
    POST   /api/auth/logout            revoke this session
    POST   /api/auth/refresh           extend the session, rotating the token
    GET    /api/auth/me                identity, org, role, permissions
    PATCH  /api/auth/me                edit your own name / phone
    GET    /api/auth/sessions          your live sessions
    DELETE /api/auth/sessions          sign out everywhere else
    POST   /api/auth/password/change   current password -> new password
    POST   /api/auth/password/forgot   mint a single-use reset token
    POST   /api/auth/password/reset    redeem it
    GET    /api/auth/roles             the role catalogue and its permissions
    GET    /api/auth/users             the roster (USER_MANAGE)
    POST   /api/auth/users             provision an account (USER_MANAGE)
    PATCH  /api/auth/users/{id}        role / enabled (ROLE_MANAGE / USER_MANAGE)

Three rules hold across all of them.

**The role never comes from the client.** Sign-up ignores any role in the body
and creates a citizen; an administrator may set a role, but only one strictly
below their own, so no path exists from "I can create users" to "I am the owner".

**Login is an oracle for nothing.** A wrong email and a wrong password return
the same 401 after the same amount of work, `forgot` returns the same body for a
known and an unknown address, and repeated failures for one email+IP hit the
CWE-307 backoff in `security.py` before they hit the database many times.

**Nothing here ever serialises a `User`.** Every response goes through
`User.as_public()`, which cannot emit the password hash.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import audit
from ..auth import (
    DEMO_ROSTER,
    DUMMY_PASSWORD_HASH,
    MIN_PASSWORD_LEN,
    auth_enabled,
    consume_password_reset,
    create_user,
    demo_password,
    get_current_user,
    get_user_by_email,
    hash_password,
    issue_password_reset,
    kdf_name,
    needs_rehash,
    password_problem,
    require_permission,
    revoke_all_sessions,
    revoke_session,
    set_password,
    set_user_role,
    start_session,
    user_permissions,
    verify_password,
)
from ..config import settings
from ..db import get_db
from ..models_db import ROLES, User, UserSession
from ..orgs import scope_query
from ..permissions import (
    DEFAULT_SIGNUP_ROLE,
    PERMISSIONS,
    ROLE_DESCRIPTIONS,
    ROLE_HOME,
    ROLE_PERMISSIONS,
    ROLE_RANK,
    outranks,
)
from ..security import login_locked, record_login_attempt

router = APIRouter(prefix="/api/auth", tags=["auth"])


# A light email shape check — full RFC validation would need email-validator,
# a dependency this project does not carry. The pattern rejects the obvious
# nonsense; correctness of the address is proven by the account existing.
_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
#: Digits, spaces and the punctuation an international number is written with.
#: Deliberately permissive: phone formats vary by country and a strict pattern
#: rejects real numbers, which is a worse failure than storing a odd-looking one.
_PHONE = r"^[0-9+()\-. ]{7,24}$"


def _meta(request: Request) -> Dict[str, Any]:
    return audit.from_request(request)


def _ip(request: Request) -> str:
    return (request.client.host if request.client else None) or "unknown"


# --------------------------------------------------------------------------
# Request models
# --------------------------------------------------------------------------


class SignupRequest(BaseModel):
    """§2 and §31. There is deliberately no `role` field: a public sign-up is
    always a citizen, so there is nothing for a client to send and nothing for
    the server to have to ignore safely."""

    full_name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=3, max_length=320, pattern=_EMAIL)
    phone: Optional[str] = Field(default=None, max_length=24, pattern=_PHONE)
    password: str = Field(min_length=1, max_length=256)
    confirm_password: str = Field(min_length=1, max_length=256)
    accept_terms: bool = Field(
        default=False,
        description="Acknowledgement of the privacy notice. Checked server-side "
                    "so it is a record rather than a checkbox in React.",
    )


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=_EMAIL)
    password: str = Field(min_length=1, max_length=256)


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=160)
    phone: Optional[str] = Field(default=None, max_length=24, pattern=_PHONE)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)
    confirm_password: str = Field(min_length=1, max_length=256)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=_EMAIL)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=128)
    new_password: str = Field(min_length=1, max_length=256)
    confirm_password: str = Field(min_length=1, max_length=256)


class NewUserRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=_EMAIL)
    password: str = Field(min_length=MIN_PASSWORD_LEN, max_length=256)
    role: str = "viewer"
    full_name: Optional[str] = Field(default=None, max_length=160)
    phone: Optional[str] = Field(default=None, max_length=24, pattern=_PHONE)
    #: An owner may place the new user in a specific org; ignored for org admins,
    #: who can only add to their own.
    org_id: Optional[int] = None


class UserUpdate(BaseModel):
    role: Optional[str] = None
    disabled: Optional[bool] = None


# --------------------------------------------------------------------------
# Session shape
# --------------------------------------------------------------------------


def _session_payload(db: Session, user: User, token: Optional[str] = None) -> Dict[str, Any]:
    """One shape for "who you are", returned by login, signup, refresh and /me.

    Four endpoints returning four subtly different user objects is how a client
    ends up with four code paths for reading a role. `permissions` is the list
    the client's `can()` reads, and `home` is where this role's dashboard lives —
    served rather than hard-coded so §23's role → route map has one definition."""
    from ..orgs import get_org

    org = get_org(db, user.org_id)
    payload: Dict[str, Any] = {
        "user": user.as_public(),
        "org": org.as_public() if org else None,
        "permissions": user_permissions(user),
        "home": ROLE_HOME.get(user.role, "/dashboard"),
        "auth_enforced": auth_enabled(),
    }
    if token is not None:
        payload["token"] = token
        payload["expires_in"] = settings.token_ttl_s
    return payload


# --------------------------------------------------------------------------
# Sign-up
# --------------------------------------------------------------------------


@router.post("/signup", status_code=201)
def signup(req: SignupRequest, request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Create a public account and open a session for it.

    The new account is a **citizen**, always. §19 is explicit that letting the
    sign-up form choose a role is the vulnerability, not the feature; police and
    administrator accounts are provisioned by an administrator or by the seed.
    """
    if not settings.signup_enabled:
        raise HTTPException(
            status_code=403,
            detail="Public sign-up is closed on this deployment. Ask an "
                   "administrator for an account.",
        )
    if req.password != req.confirm_password:
        raise HTTPException(status_code=422, detail="The two passwords don't match.")
    if not req.accept_terms:
        raise HTTPException(
            status_code=422,
            detail="Please accept the privacy notice to create an account.",
        )
    problem = password_problem(req.password, email=req.email, name=req.full_name)
    if problem:
        raise HTTPException(status_code=422, detail=problem)

    email = req.email.lower().strip()
    if get_user_by_email(db, email) is not None:
        # A duplicate is reported plainly. This does leak that an address has an
        # account — but so does any sign-up form that refuses to create a second
        # one, and the alternative (accepting and silently doing nothing) leaves
        # a person unable to sign in with no idea why.
        audit.record(
            db, "signup", actor=email, resource_type="user", success=False,
            detail="email already registered", **_meta(request),
        )
        raise HTTPException(
            status_code=409,
            detail="An account with that email already exists. Sign in instead.",
        )

    from ..orgs import get_or_create_default_org

    user = create_user(
        db,
        email,
        req.password,
        role=DEFAULT_SIGNUP_ROLE,
        org_id=get_or_create_default_org(db).id,
        full_name=req.full_name,
        phone=req.phone,
    )
    meta = _meta(request)
    audit.record(
        db, "signup", actor=user.email, actor_user_id=user.id, resource_type="user",
        resource_id=str(user.id), org_id=user.org_id,
        detail=f"role={user.role}", **meta,
    )
    token = start_session(db, user, ip=meta.get("ip"), user_agent=meta.get("user_agent"))
    return _session_payload(db, user, token)


# --------------------------------------------------------------------------
# Sign-in / sign-out
# --------------------------------------------------------------------------


@router.post("/login")
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ip = _ip(request)
    meta = _meta(request)

    # Backoff (CWE-307): after repeated failures for this email+IP, refuse for a
    # cooling-off window rather than letting a script keep guessing.
    locked = login_locked(req.email, ip)
    if locked > 0:
        audit.record(
            db, "login.failed", actor=req.email, success=False,
            detail="locked out after repeated failures", **meta,
        )
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {int(locked)}s.",
            headers={"Retry-After": str(int(locked))},
        )

    user = get_user_by_email(db, req.email)
    # Same error whether the email is unknown or the password is wrong, and the
    # password is still verified against a real hash on the miss path so timing
    # does not distinguish the two.
    ok = verify_password(req.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    if not user or not ok:
        record_login_attempt(req.email, ip, success=False)
        audit.record(db, "login.failed", actor=req.email, success=False,
                     detail="invalid email or password", **meta)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.disabled:
        # A disabled account is told so. It has already proven it holds the
        # password, so there is nothing left to conceal, and "invalid email or
        # password" would send a legitimate user round in circles.
        record_login_attempt(req.email, ip, success=False)
        audit.record(db, "login.failed", actor=user.email, actor_user_id=user.id,
                     success=False, org_id=user.org_id,
                     detail="account is disabled", **meta)
        raise HTTPException(
            status_code=403,
            detail="This account has been disabled. Contact your administrator.",
        )

    record_login_attempt(req.email, ip, success=True)

    # Transparent KDF upgrade: the password is in hand and verified exactly
    # here and nowhere else, so this is the only moment a stronger hash can be
    # written without asking anyone to reset anything.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(req.password)
        db.commit()

    token = start_session(db, user, ip=meta.get("ip"), user_agent=meta.get("user_agent"))
    audit.record(db, "login", actor=user.email, actor_user_id=user.id,
                 resource_type="session", org_id=user.org_id,
                 detail=f"role={user.role}", **meta)
    return _session_payload(db, user, token)


@router.post("/logout")
def logout(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """End this session server-side.

    Idempotent, and it answers 200 even in open mode where there is no session
    to end — a sign-out that can fail is a sign-out a user retries by clicking
    faster. The client clears its own copy of the token either way.
    """
    jti = getattr(request.state, "jti", None)
    revoked = bool(jti) and revoke_session(db, str(jti))
    audit.record(db, "logout", actor=user.email, actor_user_id=user.id,
                 resource_type="session", org_id=user.org_id,
                 detail="session revoked" if revoked else "no server session to revoke",
                 **_meta(request))
    return {"ok": True, "revoked": revoked}


@router.post("/refresh")
def refresh(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Rotate this session's token, so a long working day does not end in a
    surprise sign-out mid-investigation.

    The old session is revoked and a new one opened rather than the expiry being
    pushed out in place: a token that can be extended indefinitely is a token
    whose theft is permanent, and rotation bounds the damage to one TTL.
    """
    jti = getattr(request.state, "jti", None)
    if not jti:
        # Open mode, or a sessionless token. There is nothing to rotate; hand
        # back the current identity rather than inventing a session.
        return _session_payload(db, user)
    meta = _meta(request)
    revoke_session(db, str(jti))
    token = start_session(db, user, ip=meta.get("ip"), user_agent=meta.get("user_agent"))
    return _session_payload(db, user, token)


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------


@router.get("/me")
def me(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """The current identity, tenant, role and permissions.

    In open mode this is the seeded owner, so the UI can render a consistent
    'signed in as' without special-casing the flag.
    """
    return _session_payload(db, user)


@router.patch("/me")
def update_me(
    req: ProfileUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Edit your own profile. Name and phone only.

    Notice what is *not* here: role, org, email, disabled. Those are the fields
    whose self-service edit would be a privilege escalation, and they are absent
    from the request model rather than filtered out of it, so there is no
    version of this handler that can be talked into writing one.
    """
    changed = []
    if req.full_name is not None:
        user.full_name = req.full_name.strip() or None
        changed.append("full_name")
    if req.phone is not None:
        user.phone = req.phone.strip() or None
        changed.append("phone")
    if changed:
        db.commit()
        audit.record(db, "profile.update", actor=user.email, actor_user_id=user.id,
                     resource_type="user", resource_id=str(user.id), org_id=user.org_id,
                     detail=f"changed {', '.join(changed)}", **_meta(request))
    return _session_payload(db, user)


@router.get("/sessions")
def my_sessions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, List[Dict[str, Any]]]:
    """Every live session on this account — where it was opened and when it was
    last used. What makes "sign out everywhere" a considered action rather than
    a guess."""
    rows = (
        db.query(UserSession)
        .filter(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .order_by(UserSession.created_at.desc())
        .limit(50)
        .all()
    )
    return {"sessions": [s.as_public() for s in rows]}


@router.delete("/sessions")
def sign_out_everywhere(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Revoke every session except the one making the request."""
    jti = getattr(request.state, "jti", None)
    n = revoke_all_sessions(db, user.id, except_jti=str(jti) if jti else None)
    audit.record(db, "session.revoke_all", actor=user.email, actor_user_id=user.id,
                 resource_type="session", org_id=user.org_id,
                 detail=f"{n} session(s) revoked", **_meta(request))
    return {"revoked": n}


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------


@router.post("/password/change")
def change_password(
    req: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=422, detail="The two passwords don't match.")
    if not verify_password(req.current_password, user.password_hash):
        audit.record(db, "password.change", actor=user.email, actor_user_id=user.id,
                     resource_type="user", resource_id=str(user.id), success=False,
                     org_id=user.org_id, detail="current password incorrect",
                     **_meta(request))
        raise HTTPException(status_code=403, detail="Your current password is not correct.")
    problem = password_problem(req.new_password, email=user.email, name=user.full_name or "")
    if problem:
        raise HTTPException(status_code=422, detail=problem)

    jti = getattr(request.state, "jti", None)
    revoked = set_password(db, user, req.new_password, keep_jti=str(jti) if jti else None)
    audit.record(db, "password.change", actor=user.email, actor_user_id=user.id,
                 resource_type="user", resource_id=str(user.id), org_id=user.org_id,
                 detail=f"{revoked} other session(s) ended", **_meta(request))
    return {"ok": True, "other_sessions_ended": revoked}


@router.post("/password/forgot")
def forgot_password(
    req: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Mint a single-use reset token for an account, if it exists.

    **The response is identical either way.** A "no such account" here is an
    account-existence oracle that needs no password at all to query, which is
    strictly worse than the one `login` is careful to avoid.

    There is no mail transport in this project, so the token is written to the
    **server log** — an operator with shell access can complete a reset, which
    is the honest development story. `AEGIS_DEV_PASSWORD_RESET=1` additionally
    returns it in the response body for local work; that is refused outright
    when auth is enforced, and the response says `dev_token` so nothing can
    mistake it for a production flow.
    """
    generic = {
        "ok": True,
        "message": "If that email has an account, a reset link has been issued. "
                   "Check your inbox — and in development, the API server log.",
    }
    user = get_user_by_email(db, req.email)
    meta = _meta(request)
    if user is None or user.disabled:
        audit.record(db, "password.forgot", actor=req.email, success=False,
                     resource_type="user", detail="no such account", **meta)
        return generic

    token = issue_password_reset(db, user)
    audit.record(db, "password.forgot", actor=user.email, actor_user_id=user.id,
                 resource_type="user", resource_id=str(user.id), org_id=user.org_id,
                 detail="reset token issued", **meta)
    # The token, never the password, and never into the audit log.
    print(
        f"[aegis] password reset for {user.email}: token={token} "
        f"(valid {settings.password_reset_ttl_s}s)"
    )
    if settings.dev_password_reset and not auth_enabled():
        return {**generic, "dev_token": token, "dev_only": True}
    return generic


@router.post("/password/reset")
def reset_password(
    req: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=422, detail="The two passwords don't match.")
    user = consume_password_reset(db, req.token)
    if user is None:
        audit.record(db, "password.reset", success=False, resource_type="user",
                     detail="invalid or expired token", **_meta(request))
        raise HTTPException(
            status_code=400,
            detail="That reset link is invalid or has expired. Request a new one.",
        )
    problem = password_problem(req.new_password, email=user.email, name=user.full_name or "")
    if problem:
        # The token was already consumed, so say so — silently burning it and
        # reporting only "weak password" leaves the user with a dead link and no
        # explanation.
        raise HTTPException(
            status_code=422,
            detail=f"{problem} That reset link is now used — request a new one.",
        )
    revoked = set_password(db, user, req.new_password)
    audit.record(db, "password.reset", actor=user.email, actor_user_id=user.id,
                 resource_type="user", resource_id=str(user.id), org_id=user.org_id,
                 detail=f"{revoked} session(s) ended", **_meta(request))
    return {"ok": True, "sessions_ended": revoked}


# --------------------------------------------------------------------------
# The role catalogue
# --------------------------------------------------------------------------


@router.get("/roles")
def list_roles(_: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Every role, what it is for, and exactly what it can do.

    Served so the client renders role names and role copy from one definition
    instead of keeping a second, drifting list in TypeScript — §7's "rather than
    hard-coding role names throughout the frontend".
    """
    return {
        "roles": [
            {
                "name": name,
                "description": ROLE_DESCRIPTIONS[name],
                "rank": ROLE_RANK[name],
                "home": ROLE_HOME.get(name, "/dashboard"),
                "permissions": sorted(ROLE_PERMISSIONS[name]),
                #: Whether a public sign-up can produce this role. Exactly one
                #: can, and the UI reads it here rather than assuming.
                "self_service": name == DEFAULT_SIGNUP_ROLE,
            }
            for name in ROLES
        ],
        "permissions": [{"code": c, "description": d} for c, d in sorted(PERMISSIONS.items())],
        "signup_role": DEFAULT_SIGNUP_ROLE,
    }


@router.get("/demo-accounts")
def demo_accounts() -> Dict[str, Any]:
    """The seeded demo roster, so the sign-in screen's role switcher is not a
    hard-coded list of emails in React that drifts from what was actually seeded.

    **Empty whenever auth is enforced**, because those accounts are not created
    then — a real deployment must not have an endpoint that advertises
    credentials. The password is the configured demo password and is returned
    only in open mode, which is the mode whose entire purpose is that anyone can
    sign in and watch RBAC work.
    """
    if auth_enabled():
        return {"open_mode": False, "accounts": [], "password": None}
    return {
        "open_mode": True,
        "password": demo_password(),
        "accounts": [
            {
                "email": email,
                "role": role,
                "name": name,
                "description": ROLE_DESCRIPTIONS.get(role, ""),
                "org": "Maharashtra Cyber Cell" if org_key == "mh" else "AegisAI (default)",
            }
            for email, role, org_key, name in DEMO_ROSTER
        ]
        + [
            {
                "email": settings.default_admin_email,
                "role": "owner",
                "name": "Platform Owner",
                "description": ROLE_DESCRIPTIONS["owner"],
                "org": "AegisAI (default)",
            }
        ],
    }


# --------------------------------------------------------------------------
# User administration
# --------------------------------------------------------------------------


@router.get("/users")
def list_users(
    admin: User = Depends(require_permission("USER_MANAGE")),
    db: Session = Depends(get_db),
) -> Dict[str, List[Dict[str, Any]]]:
    # An org admin manages only their own org's users; an owner sees everyone.
    q = scope_query(db.query(User), User, admin)
    users = q.order_by(User.id.asc()).all()
    return {"users": [u.as_public() for u in users]}


@router.post("/users", status_code=201)
def add_user(
    req: NewUserRequest,
    request: Request,
    admin: User = Depends(require_permission("USER_MANAGE")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    if req.role not in ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {ROLES}")
    # Nobody may create an account at or above their own rank. This replaces the
    # narrower "only an owner may mint an owner": the old rule stopped the one
    # escalation that existed on a four-rung ladder and would not have stopped
    # an admin minting another admin, which is the same escalation one step down.
    if not outranks(admin.role, req.role):
        raise HTTPException(
            status_code=403,
            detail=f"You are {admin.role}; you can only create accounts below "
                   f"your own role.",
        )
    problem = password_problem(req.password, email=req.email, name=req.full_name or "")
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    if get_user_by_email(db, req.email):
        raise HTTPException(status_code=409, detail="A user with that email already exists")
    # New users join the creating admin's org (an owner can pass an explicit org).
    target_org = req.org_id if (admin.role == "owner" and req.org_id is not None) else admin.org_id
    user = create_user(
        db, req.email, req.password, role=req.role, org_id=target_org,
        full_name=req.full_name, phone=req.phone,
    )
    audit.record(db, "user.create", actor=admin.email, actor_user_id=admin.id,
                 target=user.email, resource_type="user", resource_id=str(user.id),
                 detail=f"role={user.role} org={target_org}", org_id=admin.org_id,
                 **_meta(request))
    return {"user": user.as_public()}


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    req: UserUpdate,
    request: Request,
    admin: User = Depends(require_permission("USER_MANAGE")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Change a user's role, or enable/disable them.

    Four guards, and each one closes a real path:

      * the target must be in a tenant this admin can see (`scope_query`), so an
        org admin cannot reach into another organisation;
      * you cannot act on yourself, so an admin cannot lock themselves out or
        quietly promote themselves;
      * you cannot act on someone at or above your own rank;
      * you cannot grant a role at or above your own rank.

    Changing a role or disabling an account **revokes every session that user
    holds**, because a demotion that leaves the old token working for another
    eleven hours is not a demotion.
    """
    target = scope_query(db.query(User), User, admin).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="No such user")
    if target.id == admin.id:
        raise HTTPException(
            status_code=403,
            detail="You cannot change your own role or status. Ask another "
                   "administrator.",
        )
    if not outranks(admin.role, target.role):
        raise HTTPException(
            status_code=403,
            detail=f"{target.email} holds {target.role}, which is not below your "
                   f"own role ({admin.role}).",
        )

    changes: List[str] = []
    if req.role is not None and req.role != target.role:
        if "ROLE_MANAGE" not in user_permissions(admin):
            raise HTTPException(status_code=403, detail="Your role does not include ROLE_MANAGE.")
        if req.role not in ROLES:
            raise HTTPException(status_code=422, detail=f"role must be one of {ROLES}")
        if not outranks(admin.role, req.role):
            raise HTTPException(
                status_code=403,
                detail=f"You are {admin.role}; you cannot grant {req.role}.",
            )
        was = target.role
        set_user_role(db, target, req.role)
        changes.append(f"role {was} -> {req.role}")
    if req.disabled is not None and req.disabled != target.disabled:
        target.disabled = req.disabled
        changes.append("disabled" if req.disabled else "re-enabled")

    if not changes:
        return {"user": target.as_public(), "changed": []}

    db.commit()
    revoked = revoke_all_sessions(db, target.id)
    audit.record(
        db, "user.update", actor=admin.email, actor_user_id=admin.id,
        target=target.email, resource_type="user", resource_id=str(target.id),
        detail="; ".join(changes) + f"; {revoked} session(s) ended",
        org_id=admin.org_id, **_meta(request),
    )
    return {"user": target.as_public(), "changed": changes, "sessions_ended": revoked}


@router.get("/status")
def auth_status() -> Dict[str, Any]:
    """What this deployment's authentication actually is — unauthenticated, so a
    sign-in screen can render the right thing before anyone has signed in.

    Facts only: no account names, no counts, nothing that helps someone who does
    not already have an account.
    """
    return {
        "enforced": auth_enabled(),
        "mode": "enforced" if auth_enabled() else "open (demo)",
        "signup_enabled": settings.signup_enabled,
        "password_hash": kdf_name(),
        "min_password_length": MIN_PASSWORD_LEN,
        "token_ttl_s": settings.token_ttl_s,
    }
