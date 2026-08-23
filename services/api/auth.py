"""
Authentication & RBAC.

Deliberately self-contained — stdlib `hashlib`/`hmac` only, no bcrypt/PyJWT — so
it adds no dependency and works offline. That is a defensible choice at this
scale, not a corner cut: pbkdf2-hmac-sha256 with a per-user salt and a high
iteration count is a standard, sound password KDF, and an HS256 token is a few
lines of HMAC. The parts that are easy to get subtly wrong are handled
explicitly: constant-time comparison everywhere (`hmac.compare_digest`),
base64url without padding, and an expiry that is always checked.

Two modes, chosen by `AEGIS_AUTH`:

  * **enforced** — protected routes require a valid bearer token, and
    `require_role` gates by the role ladder.
  * **open** (default) — `get_current_user` returns the seeded admin, so the
    demo runs with no login while every route still declares the RBAC it *would*
    enforce. Flipping the flag turns the whole thing on without touching a route.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models_db import ROLE_RANK, User

# --- password hashing -------------------------------------------------------

_PBKDF2_ITERATIONS = 240_000
_ALGO = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{_ALGO}${_PBKDF2_ITERATIONS}${_b64e(salt)}${_b64e(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters_s, salt_b64, hash_b64 = stored.split("$")
        if algo != _ALGO:
            return False
        salt = _b64d(salt_b64)
        expected = _b64d(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters_s))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk, expected)


# --- tokens (HS256, self-contained) -----------------------------------------

_dev_secret: Optional[bytes] = None


def _secret() -> bytes:
    """The signing key. A configured key is stable across restarts; without one
    a per-process key is generated so dev still works — but tokens die with the
    process, which is why production must set AEGIS_SECRET_KEY."""
    global _dev_secret
    if settings.secret_key:
        return settings.secret_key.encode("utf-8")
    if _dev_secret is None:
        _dev_secret = secrets.token_bytes(32)
        print("[aegis] AEGIS_SECRET_KEY unset — using an ephemeral dev key; "
              "tokens will not survive a restart")
    return _dev_secret


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def create_token(user: User) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": user.email,
        "uid": user.id,
        "role": user.role,
        "org": user.org_id,
        "iat": now,
        "exp": now + settings.token_ttl_s,
    }
    segments = [
        _b64e(json.dumps(header, separators=(",", ":")).encode()),
        _b64e(json.dumps(payload, separators=(",", ":")).encode()),
    ]
    signing_input = ".".join(segments).encode("ascii")
    sig = hmac.new(_secret(), signing_input, hashlib.sha256).digest()
    segments.append(_b64e(sig))
    return ".".join(segments)


def decode_token(token: str) -> Optional[dict]:
    """Return the claims if the signature is valid and the token is unexpired,
    else None. Never raises on a malformed token — a bad token is just invalid."""
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        return None
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(_secret(), signing_input, hashlib.sha256).digest()
    try:
        provided = _b64d(sig_b64)
    except (ValueError, TypeError):
        return None
    if not hmac.compare_digest(expected, provided):
        return None
    try:
        claims = json.loads(_b64d(payload_b64))
    except (ValueError, TypeError):
        return None
    if not isinstance(claims, dict) or claims.get("exp", 0) < int(time.time()):
        return None
    return claims


# --- user helpers -----------------------------------------------------------

def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email.lower().strip()).first()


def create_user(
    db: Session,
    email: str,
    password: str,
    role: str = "viewer",
    org_id: int | None = None,
) -> User:
    user = User(
        email=email.lower().strip(),
        password_hash=hash_password(password),
        role=role if role in ROLE_RANK else "viewer",
        org_id=org_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


#: Convenience accounts seeded in open (demo) mode so the role-based access
#: workflow is demonstrable without provisioning anyone by hand. All share the
#: demo password; none of these exist in enforced mode. Realistic of a cyber
#: cell: a supervisor (org admin) over analysts, plus a read-only desk (viewer),
#: and a second tenant to show cross-org isolation from the owner's seat.
DEMO_PASSWORD = "changeme"
DEMO_ROSTER = (
    # (email, role, org: "default" | "mh")
    ("supervisor@aegis.local", "admin", "default"),
    ("analyst@aegis.local", "analyst", "default"),
    ("viewer@aegis.local", "viewer", "default"),
    ("mh.admin@aegis.local", "admin", "mh"),
    ("mh.analyst@aegis.local", "analyst", "mh"),
)


def seed_admin(db: Session) -> None:
    """Seed the default org + platform owner if the user table is empty, and — in
    open (demo) mode only — a small multi-role, multi-tenant roster. Idempotent.

    The owner (`settings.default_admin_email`) is the platform superadmin: it can
    create organisations and see across them, and in open mode it is who every
    *un-authenticated* request acts as. The demo roster exists purely so the login
    screen can switch between roles and show RBAC working; it is never created
    when `AEGIS_AUTH` is on, so a real deployment ships no known-password
    accounts.
    """
    from .orgs import create_org, get_or_create_default_org

    default_org = get_or_create_default_org(db)
    if db.query(User).count() > 0:
        return

    create_user(
        db,
        settings.default_admin_email,
        settings.default_admin_password,
        role="owner",
        org_id=default_org.id,
    )
    print(f"[aegis] seeded default org {default_org.slug!r} + owner "
          f"{settings.default_admin_email!r} — change the password (AEGIS_ADMIN_PASSWORD)")

    if auth_enabled():
        return

    # Demo mode: a second tenant + a role ladder in each, so signing in as each
    # account visibly changes what the case book exposes.
    mh_org = create_org(db, "Maharashtra Cyber Cell")
    org_ids = {"default": default_org.id, "mh": mh_org.id}
    for email, role, org_key in DEMO_ROSTER:
        create_user(db, email, DEMO_PASSWORD, role=role, org_id=org_ids[org_key])
    print(f"[aegis] seeded {len(DEMO_ROSTER)} demo accounts (open mode) — "
          f"password {DEMO_PASSWORD!r}; disabled when AEGIS_AUTH=1")


# --- request dependencies ---------------------------------------------------

def auth_enabled() -> bool:
    """Indirection so tests can flip enforcement without a frozen-settings edit."""
    return settings.auth_enforced


def _open_mode_user(db: Session) -> User:
    """In open mode every request acts as the seeded admin, so routes that
    declare `require_role(...)` still work without a login."""
    seed_admin(db)
    user = db.query(User).order_by(User.id.asc()).first()
    if user is None:  # pragma: no cover - seed always creates one
        raise HTTPException(status_code=500, detail="no users provisioned")
    return user


def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    # A presented, valid token always wins — even in open mode. This is what
    # makes the demo's role switcher real: sign in as the analyst and you *are*
    # the analyst for every subsequent call, not the open-mode owner. Without
    # this, open mode returned the owner unconditionally and RBAC was invisible.
    if authorization and authorization.lower().startswith("bearer "):
        claims = decode_token(authorization.split(" ", 1)[1].strip())
        if claims is not None:
            user = db.query(User).filter(User.id == claims.get("uid")).first()
            if user is not None and not user.disabled:
                return user
        # A malformed/expired token is an error under enforcement; in open mode
        # it degrades to the open-mode identity rather than locking the demo out.
        if auth_enabled():
            raise HTTPException(status_code=401, detail="Invalid or expired token")

    if not auth_enabled():
        return _open_mode_user(db)

    raise HTTPException(status_code=401, detail="Missing bearer token")


def require_role(minimum: str):
    """Dependency factory: require at least `minimum` on the role ladder."""
    floor = ROLE_RANK.get(minimum, 0)

    def _dep(user: User = Depends(get_current_user)) -> User:
        if ROLE_RANK.get(user.role, -1) < floor:
            raise HTTPException(
                status_code=403,
                detail=f"Requires {minimum} role or higher (you are {user.role}).",
            )
        return user

    return _dep
