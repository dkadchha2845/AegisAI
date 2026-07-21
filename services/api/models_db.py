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

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from .db import Base

#: Ordered least- to most-privileged. `require_role` compares by rank.
ROLES = ("viewer", "analyst", "admin")
ROLE_RANK = {name: i for i, name in enumerate(ROLES)}


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(320), unique=True, nullable=False, index=True)
    #: pbkdf2_sha256$iterations$salt$hash — never a plaintext password.
    password_hash = Column(String(255), nullable=False)
    role = Column(String(16), nullable=False, default="viewer")
    disabled = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=_dt.datetime.utcnow)

    def as_public(self) -> dict:
        """Safe projection — never includes the password hash."""
        return {
            "id": self.id,
            "email": self.email,
            "role": self.role,
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
    created_at = Column(DateTime, nullable=False, default=_dt.datetime.utcnow)
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


class AuditEvent(Base):
    """Append-only record of who did what. Never updated, never deleted — an
    audit log that can be edited is not an audit log. The high-value events are
    the reversible-but-consequential ones: logins, evidence exports, and every
    payment hold or override."""

    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, nullable=False, default=_dt.datetime.utcnow, index=True)
    actor = Column(String(320), nullable=True)   # email, or "anonymous"/"system"
    action = Column(String(64), nullable=False, index=True)
    target = Column(String(200), nullable=True)  # session id, report id, user email…
    detail = Column(Text, nullable=True)         # short human-readable context

    def as_public(self) -> dict:
        return {
            "id": self.id,
            "ts": self.ts.isoformat() + "Z" if self.ts else None,
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "detail": self.detail,
        }
