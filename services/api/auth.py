"""
Authentication & RBAC.

Password hashing
----------------
**argon2id when `argon2-cffi` is importable, pbkdf2-hmac-sha256 otherwise**, and
the stored string says which so both verify forever. Argon2id is the preferred
KDF and the memory-hard one; pbkdf2 with a per-user salt and 240 000 iterations
is a standard, sound KDF (NIST SP 800-132) that needs nothing but the standard
library, which is what keeps the "clone it and run it offline" promise intact on
a machine that cannot build a wheel. Which one is serving is reported on
`/api/health` rather than assumed — the same rule the classifier follows.

A password verified against an older scheme is **re-hashed with the current
one** on the way through login, so installing `argon2-cffi` upgrades every
account the next time each person signs in, with no migration and no reset. The
parts that are easy to get subtly wrong are still handled explicitly:
constant-time comparison everywhere (`hmac.compare_digest`), base64url without
padding, and an expiry that is always checked.

Sessions
--------
Tokens are HS256 JWTs carried in `Authorization: Bearer`, and each one carries a
`jti` backed by a row in `user_sessions`. That row is what makes logout real: a
bearer token is otherwise valid until it expires, so a client that "signs out"
by forgetting its copy has revoked nothing. `get_current_user` refuses a token
whose session is missing, revoked or expired; `logout` revokes one;
`revoke_all_sessions` revokes every session a user holds, which is what
disabling an account and changing a password both do.

The token stays in the `Authorization` header rather than moving to an HttpOnly
cookie, and that is a decision rather than an omission. The investigation stream
is authenticated SSE read through `fetch()` precisely so no credential ends up
in a URL (see `routes/investigations.py`), the API is cross-origin from the SPA
in every deployment shape this project has, and a cookie would add a CSRF
surface to every mutating route to remove an XSS surface the strict CSP in
`security.py` already narrows. What a cookie would genuinely have bought —
revocation — is bought here instead, by the session table. The residual risk is
written down in `docs/AUTH.md` rather than papered over.

Two modes, chosen by `AEGIS_AUTH`
---------------------------------
  * **enforced** — protected routes require a valid bearer token, and
    `require_permission` gates on `permissions.ROLE_PERMISSIONS`.
  * **open** (default) — `get_current_user` returns the seeded owner, so the
    demo runs with no login while every route still declares the RBAC it *would*
    enforce. Flipping the flag turns the whole thing on without touching a route.
"""

from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import hmac
import json
import secrets
import time
from typing import Callable, List, Optional

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models_db import (
    ROLE_RANK,
    ROLES,
    Organization,
    PasswordReset,
    Permission,
    Role,
    RolePermission,
    User,
    UserSession,
)
from .permissions import (
    DEFAULT_ROLE,
    DEFAULT_SIGNUP_ROLE,
    PERMISSIONS,
    ROLE_DESCRIPTIONS,
    ROLE_PERMISSIONS,
    permissions_for,
)

# --- base64url, without padding ---------------------------------------------
# Defined first: the pbkdf2 hash format uses them, and `DUMMY_PASSWORD_HASH`
# below is built at import time.


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


# --- password hashing -------------------------------------------------------

_PBKDF2_ITERATIONS = 240_000
_PBKDF2_ALGO = "pbkdf2_sha256"

#: argon2-cffi is optional. Present => argon2id is the hashing scheme for every
#: new and re-hashed password; absent => pbkdf2. Verification handles both
#: either way, so the two installs interoperate on one database.
try:  # pragma: no cover - exercised by whichever install is running
    from argon2 import PasswordHasher as _Argon2Hasher
    from argon2.exceptions import VerificationError as _Argon2VerificationError
    from argon2.exceptions import VerifyMismatchError as _Argon2MismatchError

    # OWASP's second recommended argon2id configuration: 19 MiB, t=2, p=1.
    _ARGON2 = _Argon2Hasher(time_cost=2, memory_cost=19 * 1024, parallelism=1)
    _ARGON2_ERRORS: tuple = (_Argon2MismatchError, _Argon2VerificationError)
except Exception:  # pragma: no cover - the offline default
    _ARGON2 = None
    _ARGON2_ERRORS = ()


def kdf_name() -> str:
    """Which KDF new passwords are hashed with. Reported on /api/health."""
    return "argon2id" if _ARGON2 is not None else _PBKDF2_ALGO


def hash_password(password: str) -> str:
    if _ARGON2 is not None:
        return str(_ARGON2.hash(password))
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{_PBKDF2_ALGO}${_PBKDF2_ITERATIONS}${_b64e(salt)}${_b64e(dk)}"


def verify_password(password: str, stored: str) -> bool:
    """True if `password` produced `stored`, under whichever scheme wrote it.

    Never raises. A malformed or unknown-scheme hash is a failed verification,
    not a 500 — the row may predate this build, and a login route that crashes
    on one bad row is a denial of service against everyone.
    """
    if not stored:
        return False
    if stored.startswith("$argon2"):
        if _ARGON2 is None:
            # An argon2 hash on an install without argon2-cffi. Refuse rather
            # than pretend: the honest failure is "this deployment cannot check
            # your password", and it is visible in the logs at startup.
            return False
        try:
            return bool(_ARGON2.verify(stored, password))
        except _ARGON2_ERRORS:
            return False
        except Exception:
            return False
    try:
        algo, iters_s, salt_b64, hash_b64 = stored.split("$")
        if algo != _PBKDF2_ALGO:
            return False
        salt = _b64d(salt_b64)
        expected = _b64d(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters_s))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk, expected)


def needs_rehash(stored: str) -> bool:
    """Whether `stored` was written by a weaker scheme than the current one.

    Checked on every successful login so an install that gains `argon2-cffi`
    (or raises its parameters) upgrades accounts as their owners sign in,
    without a migration and without asking anyone to reset a password.
    """
    if _ARGON2 is not None:
        if not stored.startswith("$argon2"):
            return True
        try:
            return bool(_ARGON2.check_needs_rehash(stored))
        except Exception:
            return False
    if not stored.startswith(f"{_PBKDF2_ALGO}$"):
        return False
    try:
        return int(stored.split("$")[1]) < _PBKDF2_ITERATIONS
    except (IndexError, ValueError):
        return False


#: A real hash of a random password. `login` verifies against this when the
#: email is unknown, so a miss costs the same wall-clock time as a hit and the
#: endpoint is not a timing oracle for account existence. Built once at import
#: because building it per request would itself be the timing signal — and it is
#: a *real* hash rather than the hard-coded all-zeroes pbkdf2 string it replaces,
#: which cost nothing to verify under argon2 and reintroduced the very timing
#: difference it was written to remove.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


#: Minimum password length. Length is the control that actually matters; a
#: composition rule ("one symbol") measurably pushes people toward `Passw0rd!`.
#: The extra checks below reject the two failures a length rule alone misses.
MIN_PASSWORD_LEN = 10

_COMMON_PASSWORDS = frozenset(
    {
        "password", "password1", "password123", "passw0rd", "12345678", "123456789",
        "1234567890", "qwertyuiop", "letmein123", "iloveyou1", "admin12345",
        "aegisaegis", "changemeplease", "welcome123", "abcd123456",
    }
)


def password_problem(password: str, *, email: str = "", name: str = "") -> Optional[str]:
    """Why this password is unacceptable, or None.

    Returns the sentence a UI shows. Enforced server-side on every path that
    sets a password — sign-up, reset, change, and admin create — because a
    strength meter in React is advice, not a control.
    """
    if len(password) < MIN_PASSWORD_LEN:
        return f"Use at least {MIN_PASSWORD_LEN} characters."
    if len(password) > 256:
        return "That password is too long (256 characters maximum)."
    lowered = password.lower()
    if lowered in _COMMON_PASSWORDS:
        return "That password is too common. Choose something less guessable."
    if len(set(password)) < 5:
        return "That password repeats too few distinct characters."
    local = (email or "").split("@")[0].lower()
    if local and len(local) >= 4 and local in lowered:
        return "Don't use your email address in your password."
    for part in (name or "").lower().split():
        if len(part) >= 4 and part in lowered:
            return "Don't use your name in your password."
    return None


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


def _utcnow() -> _dt.datetime:
    """Naive UTC, matching every DateTime column in `models_db`."""
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


def create_token(user: User, *, jti: Optional[str] = None) -> str:
    """Mint a signed token for `user`.

    `jti` is optional so the unit tests that only exercise sign/verify keep
    working, and so a token can be minted for a user with no session row (open
    mode). A token *with* a jti is only accepted while its session row is live —
    see `get_current_user`.
    """
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
    if jti:
        payload["jti"] = jti
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


# --- sessions ---------------------------------------------------------------


def start_session(
    db: Session,
    user: User,
    *,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> str:
    """Open a session for `user` and return the bearer token that names it."""
    jti = secrets.token_urlsafe(16)
    now = _utcnow()
    db.add(
        UserSession(
            jti=jti,
            user_id=user.id,
            created_at=now,
            expires_at=now + _dt.timedelta(seconds=settings.token_ttl_s),
            last_seen_at=now,
            ip=ip,
            user_agent=(user_agent or "")[:256] or None,
        )
    )
    user.last_login_at = now
    db.commit()
    return create_token(user, jti=jti)


def session_for(db: Session, jti: str) -> Optional[UserSession]:
    """The live session with this id, or None if it is unknown, revoked or past
    its expiry."""
    row = db.query(UserSession).filter(UserSession.jti == jti).first()
    if row is None or row.revoked_at is not None:
        return None
    if row.expires_at <= _utcnow():
        return None
    return row


def revoke_session(db: Session, jti: str) -> bool:
    row = db.query(UserSession).filter(UserSession.jti == jti).first()
    if row is None or row.revoked_at is not None:
        return False
    row.revoked_at = _utcnow()
    db.commit()
    return True


def revoke_all_sessions(db: Session, user_id: int, *, except_jti: Optional[str] = None) -> int:
    """Revoke every live session for a user. Returns how many were closed.

    Called by "sign out everywhere", by a password change (a changed password
    must not leave a stolen token working), and by disabling an account.
    """
    q = db.query(UserSession).filter(
        UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
    )
    if except_jti:
        q = q.filter(UserSession.jti != except_jti)
    now = _utcnow()
    rows = q.all()
    for row in rows:
        row.revoked_at = now
    if rows:
        db.commit()
    return len(rows)


def purge_expired_sessions(db: Session) -> int:
    """Delete session rows that can no longer authenticate anything.

    A revoked or expired row has done its job; keeping it forever turns a
    working table into a growing one. The *audit* trail of who signed in and out
    lives in `audit_events`, which is append-only and is not touched here.
    """
    cutoff = _utcnow() - _dt.timedelta(days=7)
    n = (
        db.query(UserSession)
        .filter(UserSession.expires_at < cutoff)
        .delete(synchronize_session=False)
    )
    if n:
        db.commit()
    return int(n)


# --- user helpers -----------------------------------------------------------

def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email.lower().strip()).first()


def _role_row(db: Session, name: str) -> Optional[Role]:
    return db.query(Role).filter(Role.name == name).first()


def set_user_role(db: Session, user: User, role: str) -> None:
    """The only writer of the `role` / `role_id` pair.

    Both columns describe one fact, so one function sets both and nothing else
    assigns either. An unknown role name is refused rather than silently
    accepted — this is the function an admin's "change role" call reaches.
    """
    if role not in ROLE_PERMISSIONS:
        raise ValueError(f"unknown role {role!r}")
    user.role = role
    row = _role_row(db, role)
    user.role_id = row.id if row else None


def create_user(
    db: Session,
    email: str,
    password: str,
    role: str = DEFAULT_ROLE,
    org_id: int | None = None,
    *,
    full_name: str | None = None,
    phone: str | None = None,
) -> User:
    user = User(
        email=email.lower().strip(),
        password_hash=hash_password(password),
        org_id=org_id,
        full_name=(full_name or "").strip() or None,
        phone=(phone or "").strip() or None,
    )
    # `role` before the row is added, so an unknown role fails before anything
    # is written. The historical behaviour — an unknown role silently becoming
    # `viewer` — is kept for the legacy default only.
    set_user_role(db, user, role if role in ROLE_PERMISSIONS else DEFAULT_ROLE)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def user_permissions(user: User) -> List[str]:
    """The permission codes this user holds, sorted. What `/api/auth/me`
    returns and what the client's `can()` reads."""
    return sorted(permissions_for(user.role))


# --- seeding ----------------------------------------------------------------

#: Convenience accounts seeded in open (demo) mode so the role-based access
#: workflow is demonstrable without provisioning anyone by hand. All share the
#: demo password; none of these exist in enforced mode. Realistic of a cyber
#: cell: a supervisor (org admin) over analysts, plus a read-only desk (viewer),
#: and a second tenant to show cross-org isolation from the owner's seat.
#:
#: The first five predate the permission model and are **unchanged** — same
#: emails, same roles, same password — so anything that signed in before still
#: signs in and lands where it did. The last three are the product roles §15
#: asks for, so each of the four audiences in the specification has an account
#: to demonstrate.
MH_ORG_SLUG = "maharashtra-cyber-cell"
MH_ORG_NAME = "Maharashtra Cyber Cell"

DEMO_ROSTER = (
    # (email, role, org: "default" | "mh", full name)
    ("supervisor@aegis.local", "admin", "default", "Supervisor Demo"),
    ("analyst@aegis.local", "analyst", "default", "Analyst Demo"),
    ("viewer@aegis.local", "viewer", "default", "Viewer Demo"),
    ("mh.admin@aegis.local", "admin", "mh", "Maharashtra Admin"),
    ("mh.analyst@aegis.local", "analyst", "mh", "Maharashtra Analyst"),
    ("citizen@aegis.local", "citizen", "default", "Citizen Demo"),
    ("police@aegis.local", "police", "default", "Police Demo"),
    ("researcher@aegis.local", "researcher", "default", "Researcher Demo"),
)


def demo_password() -> str:
    """The seeded demo accounts' shared password, from configuration.

    Read through a function rather than pinned to a module constant so an
    operator can change it with `AEGIS_DEMO_PASSWORD` without editing source —
    §15 — while the default stays `changeme`, which is what the existing demo
    accounts already use and what the sign-in screen already says.
    """
    return settings.demo_password


#: Kept as a module attribute because the login screen's copy and two tests
#: refer to it by this name. It is the configured value, not a literal.
DEMO_PASSWORD = demo_password()


def seed_rbac(db: Session) -> None:
    """Reconcile the `roles`, `permissions` and `role_permissions` tables with
    `permissions.py`. Idempotent, and safe to run on every boot.

    Reconcile rather than insert-if-empty: the Python map is the authority, so a
    permission added to a role in code must appear in the database on the next
    start, and one removed must disappear. An insert-if-empty seed would leave a
    revoked grant in place on every database that had already been seeded —
    which is the same shape as the bug that broke demo login across the rename
    (see `seed_admin` below).
    """
    by_code = {p.code: p for p in db.query(Permission).all()}
    for code, description in PERMISSIONS.items():
        row = by_code.get(code)
        if row is None:
            row = Permission(code=code, description=description)
            db.add(row)
            by_code[code] = row
        elif row.description != description:
            row.description = description

    by_role = {r.name: r for r in db.query(Role).all()}
    for name in ROLE_PERMISSIONS:
        row = by_role.get(name)
        rank = ROLE_RANK[name]
        description = ROLE_DESCRIPTIONS[name]
        if row is None:
            row = Role(name=name, description=description, rank=rank)
            db.add(row)
            by_role[name] = row
        else:
            row.description = description
            row.rank = rank
    db.flush()  # ids for the join rows below

    existing = {(rp.role_id, rp.permission_id): rp for rp in db.query(RolePermission).all()}
    wanted: set[tuple[int, int]] = set()
    for name, codes in ROLE_PERMISSIONS.items():
        role_id = by_role[name].id
        for code in codes:
            wanted.add((role_id, by_code[code].id))
    for pair in wanted - set(existing):
        db.add(RolePermission(role_id=pair[0], permission_id=pair[1]))
    for pair in set(existing) - wanted:
        db.delete(existing[pair])
    db.commit()

    # Any user row whose role_id is unset or stale — a database that predates
    # the roles table, or a role renamed in code — is reconciled here, so
    # `role` and `role_id` describe one fact everywhere.
    for user in db.query(User).all():
        want = by_role.get(user.role)
        if want is not None and user.role_id != want.id:
            user.role_id = want.id
    db.commit()


def seed_admin(db: Session) -> None:
    """Seed the RBAC catalogue, the default org + platform owner, and — in open
    (demo) mode only — a small multi-role, multi-tenant roster. Idempotent.

    The owner (`settings.default_admin_email`) is the platform superadmin: it can
    create organisations and see across them, and in open mode it is who every
    *un-authenticated* request acts as. The demo roster exists purely so the login
    screen can switch between roles and show RBAC working; it is never created
    when `AEGIS_AUTH` is on, so a real deployment ships no known-password
    accounts.
    """
    from .orgs import create_org, get_or_create_default_org

    seed_rbac(db)
    default_org = get_or_create_default_org(db)

    # Per-account, not all-or-nothing. This used to be
    # `if db.query(User).count() > 0: return`, which meant that changing
    # `AEGIS_ADMIN_EMAIL` on a database that already had users silently
    # provisioned no owner at all.
    #
    # The PRESAGE -> AegisAI rename walked straight into it: the default owner
    # became admin@aegis.local, the existing database still held
    # admin@kavach.local, the early return fired, and the login screen
    # advertised credentials that did not exist. No test caught it because
    # tests seed a fresh ephemeral database, where the old branch behaved
    # identically. Seeding what is *missing* is idempotent in both cases.
    owner = db.query(User).filter(User.email == settings.default_admin_email).first()
    if owner is None:
        create_user(
            db,
            settings.default_admin_email,
            settings.default_admin_password,
            role="owner",
            org_id=default_org.id,
            full_name="Platform Owner",
        )
        print(f"[aegis] seeded default org {default_org.slug!r} + owner "
              f"{settings.default_admin_email!r} — change the password (AEGIS_ADMIN_PASSWORD)")

    if auth_enabled():
        return

    # Demo mode: a second tenant + a role ladder in each, so signing in as each
    # account visibly changes what the case book exposes. Still gated on open
    # mode, so a real deployment ships no known-password accounts.
    mh_org = (
        db.query(Organization).filter(Organization.slug == MH_ORG_SLUG).first()
        or create_org(db, MH_ORG_NAME, slug=MH_ORG_SLUG)
    )
    org_ids = {"default": default_org.id, "mh": mh_org.id}
    created = 0
    for email, role, org_key, full_name in DEMO_ROSTER:
        if db.query(User).filter(User.email == email).first() is None:
            create_user(
                db,
                email,
                demo_password(),
                role=role,
                org_id=org_ids[org_key],
                full_name=full_name,
            )
            created += 1
    if created:
        print(f"[aegis] seeded {created} demo account(s) (open mode) — "
              f"password {demo_password()!r}; disabled when AEGIS_AUTH=1")


# --- password reset ---------------------------------------------------------

def _reset_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_password_reset(db: Session, user: User) -> str:
    """Mint a single-use reset token and return it **once**.

    Only the digest is stored, so this return value is the only copy that ever
    exists. Any live reset for the same account is invalidated first: two valid
    tokens for one account doubles the window without doubling anything useful.
    """
    now = _utcnow()
    for row in (
        db.query(PasswordReset)
        .filter(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))
        .all()
    ):
        row.used_at = now
    token = secrets.token_urlsafe(32)
    db.add(
        PasswordReset(
            user_id=user.id,
            token_hash=_reset_digest(token),
            created_at=now,
            expires_at=now + _dt.timedelta(seconds=settings.password_reset_ttl_s),
        )
    )
    db.commit()
    return token


def consume_password_reset(db: Session, token: str) -> Optional[User]:
    """Redeem a reset token, returning the account it belongs to.

    The row is marked used *before* the caller sets the password, so a token
    cannot be replayed even if the write that follows fails. Returns None for an
    unknown, expired or already-used token — the caller must not distinguish
    them to the client.
    """
    row = (
        db.query(PasswordReset)
        .filter(PasswordReset.token_hash == _reset_digest(token))
        .first()
    )
    now = _utcnow()
    if row is None or row.used_at is not None or row.expires_at <= now:
        return None
    row.used_at = now
    user = db.query(User).filter(User.id == row.user_id).first()
    db.commit()
    return user


def set_password(db: Session, user: User, password: str, *, keep_jti: Optional[str] = None) -> int:
    """Set a password and end every other session. Returns sessions revoked.

    Ending the other sessions is the point: a password change that leaves a
    stolen token working has not recovered the account.
    """
    user.password_hash = hash_password(password)
    db.commit()
    return revoke_all_sessions(db, user.id, except_jti=keep_jti)


# --- request dependencies ---------------------------------------------------

def auth_enabled() -> bool:
    """Indirection so tests can flip enforcement without a frozen-settings edit."""
    return settings.auth_enforced


def _open_mode_user(db: Session) -> User:
    """In open mode every request acts as the seeded admin, so routes that
    declare `require_permission(...)` still work without a login.

    The seed runs only when the owner is actually missing. It used to run on
    every unauthenticated request, which was one cheap `INSERT ... IF NOT
    EXISTS`-shaped check per call; `seed_rbac` made it a full reconcile of three
    tables, and putting that on the request path would have traded correctness
    for a measurable cost on the demo's most common request.
    """
    # The configured owner specifically. Taking `id == 1` meant open mode acted
    # as whichever account happened to be created first — on a database that
    # predates a config change, that is not necessarily an owner, and every
    # role check would then fail for reasons no one could see.
    user = db.query(User).filter(User.email == settings.default_admin_email).first()
    if user is None:
        user = db.query(User).filter(User.role == "owner").order_by(User.id.asc()).first()
    if user is None:  # pragma: no cover - seed always creates one
        raise HTTPException(status_code=500, detail="no users provisioned")
    return user


def get_current_user(
    request: Request,
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
            if user is not None and not user.disabled and _session_ok(db, claims, request):
                # The role is read from the row, never from the token. A token
                # is a claim about who you are; what you may do is a fact about
                # the database, and a demoted user must not keep the old role
                # until their token happens to expire.
                request.state.jti = claims.get("jti")
                return user

        # A presented-and-refused credential is a 401 in **both** modes.
        #
        # This used to fall through to the open-mode identity, on the reasoning
        # that a stale token should not lock the demo out. Running the flow
        # proved that reasoning wrong in the worst possible direction: in open
        # mode, logging out, rotating a token, or being demoted left the dead
        # token authenticating — as the seeded **owner**, because that is who
        # `_open_mode_user` returns. Every session control in this module was
        # cosmetic in the default configuration, and a demoted analyst's expired
        # token was an escalation to platform superadmin.
        #
        # Open mode means "no login is *required*". It cannot also mean "a
        # rejected credential is upgraded to the highest one in the system".
        # The demo is unaffected: a request with no Authorization header at all
        # still falls through below, which is what every anonymous call makes,
        # and a client holding a dead token gets a 401 it already knows how to
        # act on — `AuthContext.refresh()` drops the token and renders signed out.
        raise HTTPException(
            status_code=401,
            detail="Your session has ended. Sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not auth_enabled():
        return _open_mode_user(db)

    raise HTTPException(
        status_code=401,
        detail="Sign in to continue.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _session_ok(db: Session, claims: dict, request: Request) -> bool:
    """Whether the session named by this token is still live.

    A token with no `jti` is accepted: `create_token` is public API, the unit
    tests mint sessionless tokens, and open mode has no session to name. A token
    that *does* name a session must have a live one — that is what makes logout
    and "sign out everywhere" real rather than cosmetic.
    """
    jti = claims.get("jti")
    if not jti:
        return True
    row = session_for(db, str(jti))
    if row is None:
        return False
    # Cheap liveness bookkeeping for the sessions list. Written at most once a
    # minute per session so a polling dashboard does not turn every GET into a
    # write.
    now = _utcnow()
    if row.last_seen_at is None or (now - row.last_seen_at).total_seconds() > 60:
        row.last_seen_at = now
        row.ip = (request.client.host if request.client else None) or row.ip
        db.commit()
    return True


def require_role(minimum: str) -> Callable[..., User]:
    """Dependency factory: require at least `minimum` on the role ladder.

    Kept because the ordinal question is still a real one and several call sites
    and tests are written against it. New route gates should use
    `require_permission`, which can express the two roles the ladder cannot.
    """
    floor = ROLE_RANK.get(minimum, 0)

    def _dep(user: User = Depends(get_current_user)) -> User:
        if ROLE_RANK.get(user.role, -1) < floor:
            raise HTTPException(
                status_code=403,
                detail=f"Requires {minimum} role or higher (you are {user.role}).",
            )
        return user

    return _dep


def require_permission(*codes: str) -> Callable[..., User]:
    """Dependency factory: require **all** of `codes`.

    All rather than any, deliberately. A gate that passes on any one of several
    permissions reads as "or" at the call site and is nearly always meant as
    "and"; where a genuine "or" is wanted — a case you own *or* one assigned to
    you — that is a decision about a row, and it belongs in the handler next to
    the query, not in a dependency that cannot see the row.

    The message names the missing capability rather than the role, because
    "requires INVESTIGATION_READ_ALL" tells an operator what to grant and
    "requires admin" tells them to over-grant.
    """
    for code in codes:
        if code not in PERMISSIONS:  # pragma: no cover - a typo fails at import
            raise ValueError(f"unknown permission {code!r}")

    def _dep(user: User = Depends(get_current_user)) -> User:
        held = permissions_for(user.role)
        missing = [c for c in codes if c not in held]
        if missing:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Your role ({user.role}) does not include "
                    f"{', '.join(missing)}."
                ),
            )
        return user

    return _dep


__all__ = [
    "DEFAULT_SIGNUP_ROLE",
    "DEMO_PASSWORD",
    "DEMO_ROSTER",
    "DUMMY_PASSWORD_HASH",
    "MIN_PASSWORD_LEN",
    "ROLES",
    "auth_enabled",
    "consume_password_reset",
    "create_token",
    "create_user",
    "decode_token",
    "demo_password",
    "get_current_user",
    "get_user_by_email",
    "hash_password",
    "issue_password_reset",
    "kdf_name",
    "needs_rehash",
    "password_problem",
    "purge_expired_sessions",
    "require_permission",
    "require_role",
    "revoke_all_sessions",
    "revoke_session",
    "seed_admin",
    "seed_rbac",
    "session_for",
    "set_password",
    "set_user_role",
    "start_session",
    "user_permissions",
    "verify_password",
]
