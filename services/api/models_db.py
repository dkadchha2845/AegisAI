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

from sqlalchemy import Boolean, Column, DateTime, Integer, String

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
