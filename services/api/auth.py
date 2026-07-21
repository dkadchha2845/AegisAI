"""
Authentication & RBAC.

Deliberately self-contained — stdlib `hashlib`/`hmac` only, no bcrypt/PyJWT — so
it adds no dependency and works offline. That is a defensible choice at this
scale, not a corner cut: pbkdf2-hmac-sha256 with a per-user salt and a high
iteration count is a standard, sound password KDF, and an HS256 token is a few
lines of HMAC. The parts that are easy to get subtly wrong are handled
explicitly: constant-time comparison everywhere (`hmac.compare_digest`),
base64url without padding, and an expiry that is always checked.

Two modes, chosen by `PRESAGE_AUTH`:

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
    process, which is why production must set PRESAGE_SECRET_KEY."""
    global _dev_secret
    if settings.secret_key:
        return settings.secret_key.encode("utf-8")
    if _dev_secret is None:
        _dev_secret = secrets.token_bytes(32)
        print("[presage] PRESAGE_SECRET_KEY unset — using an ephemeral dev key; "
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


def create_user(db: Session, email: str, password: str, role: str = "viewer") -> User:
    user = User(
        email=email.lower().strip(),
        password_hash=hash_password(password),
        role=role if role in ROLE_RANK else "viewer",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def seed_admin(db: Session) -> None:
    """Create the default admin if the user table is empty. Idempotent."""
    if db.query(User).count() > 0:
        return
    create_user(
        db,
        settings.default_admin_email,
        settings.default_admin_password,
        role="admin",
    )
    print(f"[presage] seeded default admin {settings.default_admin_email!r} — "
          "change the password (PRESAGE_ADMIN_PASSWORD)")


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
    if not auth_enabled():
        return _open_mode_user(db)

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    claims = decode_token(authorization.split(" ", 1)[1].strip())
    if claims is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.query(User).filter(User.id == claims.get("uid")).first()
    if user is None or user.disabled:
        raise HTTPException(status_code=401, detail="No such active user")
    return user


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
