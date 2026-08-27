"""
Persisted models — organisations, identity, RBAC, saved cases, and the audit log.

**Roles became a permissions table, as this file said they would.** The original
note here read: *"Roles are a strict hierarchy (viewer < analyst < admin) rather
than a set of independent permissions, because at this stage every capability
lines up on that one axis … when a capability appears that does not fit the
ladder, this becomes a permissions table"*. Two capabilities now do not fit — a
citizen who may read only their own cases, and a researcher who may read no case
at all — so `permissions.py` holds the catalogue and the role → permission map,
and the `roles` / `permissions` / `role_permissions` tables below are that map
made durable and queryable. The ladder survives in `ROLE_RANK` for the one
question that really is ordinal: who may promote whom.

**`users.role` is still the string.** It is what the token carries, what every
existing query filters on, and what `as_public()` has always returned; changing
it to an integer would have rewritten a dozen call sites to buy nothing. The
`roles` table references it by name — `roles.name` is unique, so the string *is*
a key — and `User.role_id` carries the numeric foreign key beside it for the
relational reads (`JOIN roles ON users.role_id = roles.id`) that a schema
diagram and a SQL console want. `set_user_role()` in `auth.py` is the only
writer of the pair, so the two cannot drift.
"""

from __future__ import annotations

import datetime as _dt

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from .db import Base
from .permissions import ROLE_RANK as ROLE_RANK

# `ROLES` and `ROLE_RANK` are defined in `permissions.py`, which is now the
# single definition of both, and re-exported from here because `auth.py` and
# `routes/auth.py` have always reached for them at this address. Aliased on
# import rather than imported plainly: a re-export that is never *used* in the
# module is an unused import to a linter, and `ruff --fix` will delete it.
from .permissions import ROLES as ROLES


def _utcnow() -> _dt.datetime:
    """Naive UTC timestamp for column defaults.

    `datetime.utcnow()` is deprecated from Python 3.12. This keeps the existing
    column semantics exactly — naive, in UTC — so stored values and every
    comparison against them are unchanged. Migrating the columns to
    timezone-aware `DateTime(timezone=True)` is a real schema change and
    belongs in its own commit, not in an interpreter upgrade.
    """
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


# The relative order of the four inherited roles is unchanged (viewer < analyst
# < admin < owner), so every `require_role(...)` check answers exactly as it did
# before the product roles were added — see the re-export at the top.

#: The slug of the organisation seeded on first boot. Every user and case in a
#: single-org install belongs to it, so "multi-tenant" degrades cleanly to
#: "one tenant" with no special-casing.
DEFAULT_ORG_SLUG = "aegis"


class Organization(Base):
    """A tenant. Users, saved cases, and the audit log are scoped to one of these.

    The fraud-intelligence graph (Module 2) is deliberately *not* org-scoped — it
    is shared national intelligence, and cross-jurisdiction sharing is the whole
    point of a fraud network engine. Only the platform surfaces (who can log in,
    whose case book, whose audit trail) are per-tenant.
    """

    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True)
    slug = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    def as_public(self) -> dict:
        return {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class Role(Base):
    """The role catalogue, as rows.

    The authority on what a role *can do* is `permissions.ROLE_PERMISSIONS` — a
    Python literal that a security review can read top to bottom and that cannot
    be edited by anything with a database connection. These rows are that map
    projected into the database so the schema is relational and inspectable
    (`SELECT * FROM roles JOIN role_permissions …` answers "who can manage
    users" in a SQL console), and so the API can serve role metadata without the
    frontend hard-coding a list of role names. `seed_rbac()` reconciles them on
    every boot; editing a row by hand changes the description, never the grant.
    """

    __tablename__ = "roles"

    id = Column(Integer, primary_key=True)
    name = Column(String(32), unique=True, nullable=False, index=True)
    description = Column(String(400), nullable=False, default="")
    #: The ladder position, mirrored from `ROLE_RANK` so an ORDER BY in a
    #: console sorts roles the way the escalation guard reasons about them.
    rank = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    def as_public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "rank": self.rank,
        }


class Permission(Base):
    """One capability. `code` is the string every `require_permission` gate names."""

    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True)
    code = Column(String(48), unique=True, nullable=False, index=True)
    description = Column(String(400), nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    def as_public(self) -> dict:
        return {"id": self.id, "code": self.code, "description": self.description}


class RolePermission(Base):
    """Which role holds which permission. The join table, reconciled from
    `permissions.ROLE_PERMISSIONS` on every boot."""

    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, index=True)
    permission_id = Column(Integer, ForeignKey("permissions.id"), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_pair"),
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(320), unique=True, nullable=False, index=True)
    #: argon2id, or pbkdf2_sha256$iterations$salt$hash where argon2-cffi is not
    #: installed. Never a plaintext password, and never sent to a client — see
    #: `as_public()`, which is the only projection any route may return.
    password_hash = Column(String(255), nullable=False)
    role = Column(String(16), nullable=False, default="viewer")
    #: The numeric key for the same fact, kept in step by `auth.set_user_role`.
    #: Nullable because a row written before the RBAC tables existed has no
    #: role_id until the migration backfills it, and because `users` is created
    #: before `roles` is populated on a first boot.
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=True, index=True)
    #: The tenant this user belongs to. Nullable only so an owner can be
    #: org-less (platform-level); every normal user has one.
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)

    #: Profile. All nullable: every account that existed before sign-up did has
    #: none of them, and an account is perfectly usable without them.
    full_name = Column(String(160), nullable=True)
    phone = Column(String(32), nullable=True)
    avatar_url = Column(String(512), nullable=True)

    disabled = Column(Boolean, nullable=False, default=False)
    #: False for everyone today. There is no mail transport configured, so
    #: nothing verifies an address, and the column says so rather than claiming
    #: a check that never happened — no route gates on it.
    email_verified = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    last_login_at = Column(DateTime, nullable=True)

    def display_name(self) -> str:
        """What a UI puts next to the avatar. The local part of the email is a
        better fallback than the whole address in a 120px chip."""
        if self.full_name and self.full_name.strip():
            return self.full_name.strip()
        return (self.email or "").split("@")[0] or "user"

    def as_public(self) -> dict:
        """Safe projection — never includes the password hash.

        This is the *only* shape of a user that leaves the process. Every route
        that returns a user returns this; nothing anywhere serialises the model
        directly, which is what keeps `password_hash` off the wire by
        construction rather than by remembering.
        """
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "display_name": self.display_name(),
            "phone": self.phone,
            "avatar_url": self.avatar_url,
            "role": self.role,
            "role_id": self.role_id,
            "org_id": self.org_id,
            "disabled": self.disabled,
            "email_verified": self.email_verified,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "updated_at": self.updated_at.isoformat() + "Z" if self.updated_at else None,
            "last_login_at": self.last_login_at.isoformat() + "Z" if self.last_login_at else None,
        }


class UserSession(Base):
    """One issued token, so that signing out actually ends a session.

    A bearer JWT is valid until it expires; a client that "logs out" by deleting
    its copy has revoked nothing, and a token stolen before that moment keeps
    working for the rest of its twelve hours. This table is the other half:
    every token carries a `jti`, `get_current_user` refuses one whose row is
    missing or revoked, and `POST /api/auth/logout` sets `revoked_at`.

    The token itself is never stored — only its id. A session table that holds
    tokens is a table whose disclosure is equivalent to the disclosure of every
    live credential in it.
    """

    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True)
    #: The token's `jti` claim. Random, 128 bits, unique.
    jti = Column(String(48), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow, index=True)
    #: When the token stops being accepted regardless of this row.
    expires_at = Column(DateTime, nullable=False)
    #: Set on logout, on "sign out everywhere", and when an admin disables the
    #: account. Non-null means "refuse this token".
    revoked_at = Column(DateTime, nullable=True)
    #: Last time this session was seen on a request — what a "your sessions"
    #: list shows, and what makes an abandoned session visible.
    last_seen_at = Column(DateTime, nullable=True)
    ip = Column(String(64), nullable=True)
    #: Truncated on write. A user agent is attacker-controlled free text, and
    #: an unbounded column that accepts it is a storage-exhaustion primitive.
    user_agent = Column(String(256), nullable=True)

    def as_public(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "expires_at": self.expires_at.isoformat() + "Z" if self.expires_at else None,
            "last_seen_at": self.last_seen_at.isoformat() + "Z" if self.last_seen_at else None,
            "revoked": self.revoked_at is not None,
            "ip": self.ip,
            "user_agent": self.user_agent,
        }


class PasswordReset(Base):
    """A single-use password-reset grant.

    The token is stored as a SHA-256 digest, never in the clear, for the same
    reason a password is: a reset token is a bearer credential for an account,
    so a dump of this table must not be a dump of working credentials. Rows are
    single use (`used_at`) and short-lived (`expires_at`).
    """

    __tablename__ = "password_resets"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    #: sha256(token), hex. The token itself is only ever in the response that
    #: minted it and in the operator's log line.
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)


class CaseRecord(Base):
    """A saved evidence package — the durable case file behind an escalation.

    The full package is kept verbatim as JSON so a saved case is exactly what
    was exported, byte for byte; the flat columns alongside it exist only so the
    list view can sort and filter without parsing every blob.
    """

    __tablename__ = "case_records"

    id = Column(Integer, primary_key=True)
    report_id = Column(String(32), unique=True, nullable=False, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    #: Owning tenant — the case book only shows cases from the viewer's own org.
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    created_by = Column(String(320), nullable=True)  # actor email (null in some open-mode paths)
    caller_number = Column(String(64), nullable=True)
    incident_type = Column(String(200), nullable=True)
    peak_threat = Column(Float, nullable=True)
    final_level = Column(String(16), nullable=True)
    #: The full evidence package, as returned by build_evidence_package.
    package_json = Column(Text, nullable=False)

    def as_summary(self) -> dict:
        return {
            "report_id": self.report_id,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "created_by": self.created_by,
            "caller_number": self.caller_number,
            "incident_type": self.incident_type,
            "peak_threat": self.peak_threat,
            "final_level": self.final_level,
        }


class CitizenReport(Base):
    """A citizen's preserved submission (CFSRP / Module 3, Step 5 — Evidence Vault).

    When someone checks a suspicious message or call through the Shield, the
    verification result plus whatever they submitted is preserved here so it can
    later be turned into a cybercrime complaint. The `token` is an unguessable
    public handle: a citizen has no account in the demo, so the vault is reached
    by holding the token rather than by a session — which is why it must be
    random and why nothing sensitive is keyed on a sequential id.
    """

    __tablename__ = "citizen_reports"

    id = Column(Integer, primary_key=True)
    token = Column(String(48), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    channel = Column(String(24), nullable=False, default="web")  # web | whatsapp | app
    city = Column(String(80), nullable=True)
    caller_number = Column(String(64), nullable=True)
    upi_id = Column(String(128), nullable=True)
    verdict = Column(String(32), nullable=True)
    level = Column(String(16), nullable=True)
    score = Column(Float, nullable=True)
    scam_stage = Column(String(32), nullable=True)
    #: The full verification result (Module 1 + Module 2 fusion), verbatim.
    result_json = Column(Text, nullable=False)

    def as_summary(self) -> dict:
        return {
            "token": self.token,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "channel": self.channel,
            "city": self.city,
            "caller_number": self.caller_number,
            "upi_id": self.upi_id,
            "verdict": self.verdict,
            "level": self.level,
            "score": self.score,
            "scam_stage": self.scam_stage,
        }


class AuditEvent(Base):
    """Append-only record of who did what. Never updated, never deleted — an
    audit log that can be edited is not an audit log. The high-value events are
    the reversible-but-consequential ones: logins, evidence exports, every
    payment hold or override, and every change to who can do what.

    **Nothing secret is ever written here.** Not a password, not a token, not a
    reset token, not a password hash. `detail` is short human-readable context
    written by the call site, and the call sites are the whole of this service —
    so the rule is stated here, at the table, rather than trusted to memory at
    each of them. `audit.record()` is the only writer.
    """

    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, nullable=False, default=_utcnow, index=True)
    #: Owning tenant — an org admin sees only their own org's activity.
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    actor = Column(String(320), nullable=True)   # email, or "anonymous"/"system"
    #: The acting account, when there is one. Kept *beside* `actor` rather than
    #: replacing it: a failed login has an email and no user, an account can be
    #: deleted while its trail must survive, and an email is what an operator
    #: reads. Nullable, and never a foreign-key cascade — an audit row that
    #: disappears with its subject is not an audit row.
    actor_user_id = Column(Integer, nullable=True, index=True)
    action = Column(String(64), nullable=False, index=True)
    #: What kind of thing was acted on — "user", "investigation", "report",
    #: "session", "organization". Free text, indexed, so the log can be filtered
    #: by resource class rather than by guessing at `action` prefixes.
    resource_type = Column(String(32), nullable=True, index=True)
    resource_id = Column(String(200), nullable=True)
    target = Column(String(200), nullable=True)  # session id, report id, user email…
    #: Whether the attempt succeeded. A log that only records successes cannot
    #: answer the question an audit log is usually opened to answer.
    success = Column(Boolean, nullable=False, default=True)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(256), nullable=True)
    detail = Column(Text, nullable=True)         # short human-readable context

    def as_public(self) -> dict:
        return {
            "id": self.id,
            "ts": self.ts.isoformat() + "Z" if self.ts else None,
            "org_id": self.org_id,
            "actor": self.actor,
            "actor_user_id": self.actor_user_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "target": self.target,
            "success": self.success,
            "ip": self.ip,
            "user_agent": self.user_agent,
            "detail": self.detail,
        }
