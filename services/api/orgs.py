"""
Organisation helpers — tenancy, kept backward compatible.

Single-org installs never touch most of this: a default organisation is seeded on
first boot, the seeded admin owns it, and every case / audit row is stamped with
it. The multi-tenant behaviour only *appears* when an owner creates a second org
and adds users to it. That is the design goal — "multi-tenant" that degrades to
"one tenant" with no special-casing and no change to the existing demo.

Scoping rule, applied everywhere the platform reads tenant data: an `owner` sees
across all organisations (they administer the platform); everyone else is
filtered to their own `org_id`. A user with no org sees nothing tenant-scoped —
which is the safe default, not an accident.
"""

from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

from .models_db import DEFAULT_ORG_SLUG, Organization, User


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:64] or "org"


def get_or_create_default_org(db: Session) -> Organization:
    """The tenant every single-org install lives in. Idempotent."""
    org = db.query(Organization).filter(Organization.slug == DEFAULT_ORG_SLUG).first()
    if org is None:
        org = Organization(slug=DEFAULT_ORG_SLUG, name="AegisAI (default)")
        db.add(org)
        db.commit()
        db.refresh(org)
    return org


def create_org(db: Session, name: str, slug: Optional[str] = None) -> Organization:
    s = slug or slugify(name)
    # Ensure uniqueness by suffixing if needed — two "Delhi Cyber Cell" orgs are
    # plausible and must not collide on the slug.
    base, n = s, 1
    while db.query(Organization).filter(Organization.slug == s).first() is not None:
        n += 1
        s = f"{base}-{n}"
    org = Organization(slug=s, name=name)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def get_org(db: Session, org_id: Optional[int]) -> Optional[Organization]:
    if org_id is None:
        return None
    return db.query(Organization).filter(Organization.id == org_id).first()


def is_platform_owner(user: User) -> bool:
    return user.role == "owner"


def scope_query(query, model, user: User):
    """Restrict a query on a tenant-scoped model to what `user` may see.

    An owner is unfiltered (platform-wide). Anyone else is filtered to their own
    org. This is the single choke point for tenant isolation — every list/read of
    cases or audit goes through it, so there is one place to be right about IDOR.
    """
    if is_platform_owner(user):
        return query
    return query.filter(model.org_id == user.org_id)
