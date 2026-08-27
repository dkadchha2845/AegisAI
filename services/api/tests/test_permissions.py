"""
The permission catalogue, checked as data.

These are unit tests over `permissions.py` and the seeding that projects it into
the database. They are separate from `test_rbac.py`, which drives the same
matrix through HTTP: a wrong answer here is a wrong *policy*, and a wrong answer
there is a route that failed to apply the policy. Told apart, they say which.

The most important test in this file is
`test_the_inherited_roles_keep_exactly_what_the_ladder_gave_them`. The whole
risk of replacing a rank comparison with a permission set is that some role
silently gains or loses a capability in the translation, and the four inherited
roles are the ones with live accounts and a working demo behind them.
"""

from __future__ import annotations

import pytest

from services.api.permissions import (
    PERMISSIONS,
    ROLE_DESCRIPTIONS,
    ROLE_HOME,
    ROLE_PERMISSIONS,
    ROLE_RANK,
    ROLES,
    has_permission,
    outranks,
    permissions_for,
)

# --- the catalogue is internally consistent ---------------------------------


def test_every_granted_code_exists():
    granted = {c for codes in ROLE_PERMISSIONS.values() for c in codes}
    assert granted <= set(PERMISSIONS)


def test_every_permission_is_granted_to_someone():
    """A permission no role holds is a route nobody can reach. The import-time
    guard in permissions.py already refuses it; this states why."""
    granted = {c for codes in ROLE_PERMISSIONS.values() for c in codes}
    assert set(PERMISSIONS) - granted == set()


def test_every_role_has_a_description_a_rank_and_a_home():
    for name in ROLES:
        assert ROLE_DESCRIPTIONS[name].strip()
        assert name in ROLE_RANK
        assert ROLE_HOME[name].startswith("/")


def test_unknown_role_holds_nothing():
    """A row carrying a role this build does not know about locks that account
    out of everything, rather than raising on every request it makes."""
    assert permissions_for("wizard") == frozenset()
    assert not has_permission("wizard", "USER_MANAGE")


# --- the inherited roles are unchanged --------------------------------------


def test_the_inherited_roles_keep_exactly_what_the_ladder_gave_them():
    """viewer < analyst < admin < owner, still, and still nested.

    The ladder's defining property was that each rung was a superset of the one
    below. If the translation to permission sets broke that, an account that
    could do something yesterday cannot do it today — which is the regression
    this change is most likely to cause and least likely to notice.
    """
    viewer = permissions_for("viewer")
    analyst = permissions_for("analyst")
    admin = permissions_for("admin")
    owner = permissions_for("owner")
    assert viewer < analyst < admin < owner


def test_the_relative_order_of_the_inherited_roles_is_unchanged():
    assert ROLE_RANK["viewer"] < ROLE_RANK["analyst"] < ROLE_RANK["admin"] < ROLE_RANK["owner"]


def test_viewer_reads_the_org_and_writes_nothing():
    v = permissions_for("viewer")
    assert {"INVESTIGATION_READ_ALL", "REPORT_READ_ALL", "GRAPH_READ"} <= v
    assert not (
        {"INVESTIGATION_CREATE", "REPORT_CREATE", "USER_MANAGE", "INVESTIGATION_DELETE"} & v
    )


def test_analyst_can_investigate_and_save_but_not_administer():
    a = permissions_for("analyst")
    assert {"INVESTIGATION_CREATE", "REPORT_CREATE", "EVIDENCE_UPLOAD"} <= a
    assert not ({"USER_MANAGE", "ROLE_MANAGE", "AUDIT_READ", "ORG_MANAGE"} & a)


def test_only_the_owner_manages_organisations():
    holders = [r for r in ROLES if has_permission(r, "ORG_MANAGE")]
    assert holders == ["owner"]


# --- the product roles ------------------------------------------------------


def test_citizen_reads_only_their_own_and_never_the_graph():
    """§7 and §24. A citizen investigates and reads their own; they do not read
    another person's case and they do not read entity-level intelligence."""
    c = permissions_for("citizen")
    assert {"INVESTIGATION_CREATE", "INVESTIGATION_READ_OWN", "REPORT_READ_OWN"} <= c
    assert not (
        {
            "INVESTIGATION_READ_ALL",
            "INVESTIGATION_READ_ASSIGNED",
            "REPORT_READ_ALL",
            "GRAPH_READ",
            "USER_MANAGE",
            "ROLE_MANAGE",
            "AUDIT_READ",
            "INVESTIGATION_DELETE",
        }
        & c
    )


def test_citizen_still_sees_aggregate_awareness():
    """The 'what is going around' figures the landing page and Home have always
    shown everybody. Withdrawing them from citizens would have been a silent
    regression of two existing screens."""
    assert has_permission("citizen", "THREAT_INTEL_READ")


def test_researcher_reads_no_case_of_any_kind():
    """§27, and the reason a researcher is not a rung on the ladder: they hold
    something `viewer` does not and lack everything `viewer` has."""
    r = permissions_for("researcher")
    assert "RESEARCH_READ" in r
    case_level = {
        "INVESTIGATION_READ_OWN",
        "INVESTIGATION_READ_ASSIGNED",
        "INVESTIGATION_READ_ALL",
        "REPORT_READ_OWN",
        "REPORT_READ_ASSIGNED",
        "REPORT_READ_ALL",
        "EVIDENCE_READ",
        "GRAPH_READ",
    }
    assert not (case_level & r)


def test_researcher_is_beside_the_ladder_not_on_it():
    researcher = permissions_for("researcher")
    viewer = permissions_for("viewer")
    assert not researcher <= viewer
    assert not viewer <= researcher


def test_police_is_an_investigator_and_not_an_administrator():
    """§25: 'Cannot arbitrarily become admin.'"""
    p = permissions_for("police")
    assert permissions_for("analyst") <= p
    assert {"INVESTIGATION_READ_ASSIGNED", "REPORT_READ_ASSIGNED"} <= p
    assert not ({"USER_MANAGE", "ROLE_MANAGE", "AUDIT_READ", "ORG_MANAGE"} & p)


def test_admin_administers_its_own_org_and_not_the_platform():
    a = permissions_for("admin")
    assert {"USER_MANAGE", "ROLE_MANAGE", "AUDIT_READ", "INVESTIGATION_DELETE"} <= a
    assert "ORG_MANAGE" not in a


# --- the escalation guard ---------------------------------------------------


@pytest.mark.parametrize(
    ("actor", "target", "allowed"),
    [
        ("owner", "admin", True),
        ("owner", "owner", False),
        ("admin", "analyst", True),
        ("admin", "admin", False),
        ("admin", "owner", False),
        ("analyst", "viewer", True),
        ("analyst", "analyst", False),
        ("police", "analyst", False),   # peers, not a rung apart
        ("citizen", "citizen", False),
    ],
)
def test_outranks(actor, target, allowed):
    assert outranks(actor, target) is allowed


def test_nobody_outranks_the_owner():
    assert [r for r in ROLES if outranks(r, "owner")] == []


# --- the database projection ------------------------------------------------


def _fresh_db():
    from services.api.db import SessionLocal, init_db

    init_db()
    return SessionLocal()


def test_seeding_projects_the_map_into_the_tables():
    from services.api.auth import seed_rbac
    from services.api.models_db import Permission, Role, RolePermission

    db = _fresh_db()
    try:
        seed_rbac(db)
        assert {r.name for r in db.query(Role).all()} == set(ROLES)
        assert {p.code for p in db.query(Permission).all()} == set(PERMISSIONS)

        roles = {r.id: r.name for r in db.query(Role).all()}
        perms = {p.id: p.code for p in db.query(Permission).all()}
        pairs = {
            (roles[rp.role_id], perms[rp.permission_id])
            for rp in db.query(RolePermission).all()
        }
        expected = {(name, code) for name, codes in ROLE_PERMISSIONS.items() for code in codes}
        assert pairs == expected
    finally:
        db.close()


def test_seeding_is_idempotent_and_reconciles_rather_than_appends():
    """Running it twice changes nothing, and a grant removed from the map is
    removed from the table.

    The second half is the one that matters. An insert-if-missing seed leaves a
    revoked grant in place on every database that has already been seeded, which
    is the same shape as the bug that broke demo login across the rename — the
    fix was to reconcile what is *missing or wrong* rather than to skip when
    something is already there.
    """
    from services.api.auth import seed_rbac
    from services.api.models_db import Permission, Role, RolePermission

    db = _fresh_db()
    try:
        seed_rbac(db)
        before = db.query(RolePermission).count()
        seed_rbac(db)
        assert db.query(RolePermission).count() == before

        # Forge a grant the map does not contain: citizen -> USER_MANAGE.
        citizen = db.query(Role).filter(Role.name == "citizen").one()
        manage = db.query(Permission).filter(Permission.code == "USER_MANAGE").one()
        db.add(RolePermission(role_id=citizen.id, permission_id=manage.id))
        db.commit()
        assert db.query(RolePermission).count() == before + 1

        seed_rbac(db)
        assert db.query(RolePermission).count() == before
        forged = (
            db.query(RolePermission)
            .filter(
                RolePermission.role_id == citizen.id,
                RolePermission.permission_id == manage.id,
            )
            .first()
        )
        assert forged is None
    finally:
        db.close()


def test_seeding_reconciles_a_users_role_id():
    """`users.role` and `users.role_id` describe one fact, so a row whose
    numeric key is missing or stale is repaired rather than left to disagree."""
    from services.api.auth import create_user, seed_rbac
    from services.api.models_db import Role

    db = _fresh_db()
    try:
        seed_rbac(db)
        user = create_user(db, "rolekey@aegis.local", "quiet-harbour-73", role="analyst")
        user.role_id = None
        db.commit()

        seed_rbac(db)
        db.refresh(user)
        analyst = db.query(Role).filter(Role.name == "analyst").one()
        assert user.role_id == analyst.id
    finally:
        db.close()
