"""
Persisted models. Single-org RBAC to start — one organisation, three roles.

Roles are a strict hierarchy (viewer < analyst < admin) rather than a set of
independent permissions, because at this stage every capability lines up on that
one axis: a viewer reads, an analyst acts (exports, payment overrides), an admin
manages users. When a capability appears that does not fit the ladder, this
becomes a permissions table; until then a ladder is the honest model.
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
)

from .db import Base


def _utcnow() -> _dt.datetime:
    """Naive UTC timestamp for column defaults.

    `datetime.utcnow()` is deprecated from Python 3.12. This keeps the existing
    column semantics exactly — naive, in UTC — so stored values and every
    comparison against them are unchanged. Migrating the columns to
    timezone-aware `DateTime(timezone=True)` is a real schema change and
    belongs in its own commit, not in an interpreter upgrade.
    """
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


#: Ordered least- to most-privileged. `require_role` compares by rank.
#: viewer < analyst < admin are *within-org* roles; `owner` is the platform
#: superadmin that manages organisations themselves and can see across them.
#: Adding `owner` at the top is backward compatible: every existing check
#: (`require_role("admin")`) still passes for an owner, and single-org installs
#: never mint one.
ROLES = ("viewer", "analyst", "admin", "owner")
ROLE_RANK = {name: i for i, name in enumerate(ROLES)}

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


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(320), unique=True, nullable=False, index=True)
    #: pbkdf2_sha256$iterations$salt$hash — never a plaintext password.
    password_hash = Column(String(255), nullable=False)
    role = Column(String(16), nullable=False, default="viewer")
    #: The tenant this user belongs to. Nullable only so an owner can be
    #: org-less (platform-level); every normal user has one.
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    disabled = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    def as_public(self) -> dict:
        """Safe projection — never includes the password hash."""
        return {
            "id": self.id,
            "email": self.email,
            "role": self.role,
            "org_id": self.org_id,
            "disabled": self.disabled,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


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
    the reversible-but-consequential ones: logins, evidence exports, and every
    payment hold or override."""

    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, nullable=False, default=_utcnow, index=True)
    #: Owning tenant — an org admin sees only their own org's activity.
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    actor = Column(String(320), nullable=True)   # email, or "anonymous"/"system"
    action = Column(String(64), nullable=False, index=True)
    target = Column(String(200), nullable=True)  # session id, report id, user email…
    detail = Column(Text, nullable=True)         # short human-readable context

    def as_public(self) -> dict:
        return {
            "id": self.id,
            "ts": self.ts.isoformat() + "Z" if self.ts else None,
            "org_id": self.org_id,
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "detail": self.detail,
        }
