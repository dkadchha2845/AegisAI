"""
The permission catalogue, and the roles that hold each permission.

**Why this exists.** Until now a role was a rank on a ladder
(`viewer < analyst < admin < owner`) and every route asked "are you at least
X?". That was the honest model while every capability lined up on one axis —
`models_db.ROLES` said as much, and said what would replace it: *"when a
capability appears that does not fit the ladder, this becomes a permissions
table"*. Two capabilities now do not fit.

A **citizen** may create an investigation and read their own, and may not read
anyone else's — so they are simultaneously above and below `viewer`, which the
ladder cannot express. A **researcher** may read aggregate fraud statistics and
model evaluation and must never read a case, so they are beside the ladder
rather than on it. Ranking either of them is a lie that the next route to be
written would believe.

**What it is.** One flat set of permission codes, and one explicit map from role
to the codes it holds. No inheritance, no wildcards: `ROLE_PERMISSIONS` is read
top-to-bottom as the complete answer to "what can this role do", which is the
property that makes a security review of it possible at all. The sets are built
from named unions so a reader can see that `police` is `analyst` plus three
things rather than having to diff two twenty-line literals.

**What still uses the ladder.** `ROLE_RANK` survives, and `require_role` with
it, for two jobs that are genuinely ordinal and not permission-shaped: who may
create or promote whom (an admin must not mint an owner), and the legacy
`require_role` gate that older call sites and tests exercise. The relative order
of the four original roles is unchanged, so every existing check answers exactly
as it did.

**How it is evaluated.** `tests/test_permissions.py` asserts the catalogue and
the map are internally consistent (every granted code exists; every code is
granted to someone), that the four inherited roles keep the exact capability set
the ladder gave them, and that the four product roles are refused what §38 of
the specification says they must be refused. `tests/test_rbac.py` drives the
same matrix through the running app.

**Limitations, stated.** Permissions are per-role, not per-user: there are no
per-user grants and no deny rules, so "this one analyst may also read the audit
log" is not expressible without a new role. Resource *ownership* is deliberately
not a permission — `INVESTIGATION_READ_OWN` says you may read cases you created,
and the check that a given case is yours lives at the query, not here, because a
permission that has to be evaluated against a row is an access-control decision
wearing a permission's clothes.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Tuple

# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------

#: Every permission code in the system, with the sentence a UI can show beside
#: it. A code that is not in this dict cannot be granted — `ROLE_PERMISSIONS` is
#: validated against it at import time, so a typo in a role's grant list is an
#: ImportError at startup rather than a silent hole.
PERMISSIONS: Dict[str, str] = {
    # --- investigations ----------------------------------------------------
    "INVESTIGATION_CREATE": "Start an investigation by submitting evidence.",
    "INVESTIGATION_READ_OWN": "Read investigations you created.",
    "INVESTIGATION_READ_ASSIGNED": "Read investigations assigned to you.",
    "INVESTIGATION_READ_ALL": "Read every investigation in your organisation.",
    "INVESTIGATION_UPDATE": "Change a case's status or add investigation notes.",
    "INVESTIGATION_DELETE": "Erase an investigation and the bytes of its evidence.",
    # --- evidence ----------------------------------------------------------
    "EVIDENCE_UPLOAD": "Attach files to an investigation.",
    "EVIDENCE_READ": "Read the artefacts attached to a case you can see.",
    # --- analysis surfaces -------------------------------------------------
    "ANALYZE_USE": "Run the analyzer on a message, screenshot, number or UPI ID.",
    "LIVE_SESSION_USE": "Run a live protected call and act on its guidance.",
    # --- intelligence ------------------------------------------------------
    "THREAT_INTEL_READ": "Read aggregate fraud statistics and hotspots.",
    "THREAT_INTEL_MANAGE": "Rebuild the fraud graph and curate its intelligence.",
    "GRAPH_READ": "Read the knowledge graph — clusters, entities, link predictions.",
    # --- reports -----------------------------------------------------------
    "REPORT_CREATE": "Save an evidence package as a durable case file.",
    "REPORT_READ_OWN": "Read case files you saved.",
    "REPORT_READ_ASSIGNED": "Read case files assigned to you.",
    "REPORT_READ_ALL": "Read every case file in your organisation.",
    # --- administration ----------------------------------------------------
    "USER_MANAGE": "Create, disable and edit user accounts.",
    "ROLE_MANAGE": "Change which role a user holds.",
    "ORG_MANAGE": "Create organisations and see across them.",
    "AUDIT_READ": "Read the audit log.",
    "AGENT_CONFIG": "Read agent configuration and system settings.",
    # --- research ----------------------------------------------------------
    "RESEARCH_READ": "Read anonymised datasets, model evaluation and fraud trends.",
}


def _codes(*names: str) -> FrozenSet[str]:
    return frozenset(names)


# ---------------------------------------------------------------------------
# The roles
# ---------------------------------------------------------------------------

#: A citizen: the person the product exists for. They may investigate what
#: happened to them and read what came back, and they may read the aggregate
#: "what is going around" intelligence the landing page and Home already show
#: everybody. They may not read another person's case, and nothing here grants
#: a read of the knowledge graph, which is entity-level and therefore personal.
_CITIZEN = _codes(
    "INVESTIGATION_CREATE",
    "INVESTIGATION_READ_OWN",
    "EVIDENCE_UPLOAD",
    "EVIDENCE_READ",
    "ANALYZE_USE",
    "LIVE_SESSION_USE",
    "THREAT_INTEL_READ",
    "REPORT_CREATE",
    "REPORT_READ_OWN",
)

#: The inherited read-only desk. Exactly what `require_role("viewer")` opened
#: before this module existed: every case in the organisation, the graph, the
#: intel console. Read-only — no create, no save, no admin.
_VIEWER = _codes(
    "INVESTIGATION_READ_OWN",
    "INVESTIGATION_READ_ALL",
    "EVIDENCE_READ",
    "ANALYZE_USE",
    "THREAT_INTEL_READ",
    "GRAPH_READ",
    "REPORT_READ_OWN",
    "REPORT_READ_ALL",
)

#: Academic / evaluation access. Aggregates, metrics and model cards, and
#: **no** case-level read of any kind — which is why this is not a rung above
#: `viewer` but a different set entirely.
_RESEARCHER = _codes(
    "RESEARCH_READ",
    "THREAT_INTEL_READ",
    "ANALYZE_USE",
)

#: The inherited analyst. Viewer plus the two things the ladder gave rank 1:
#: submit an investigation, and save an evidence package.
_ANALYST = _VIEWER | _codes(
    "INVESTIGATION_CREATE",
    "INVESTIGATION_UPDATE",
    "EVIDENCE_UPLOAD",
    "LIVE_SESSION_USE",
    "REPORT_CREATE",
)

#: An authorised investigator. The analyst set plus the case-work an
#: investigator does that an analyst does not: assigned-case reads and their
#: reports. Deliberately **not** granted `USER_MANAGE`, `ROLE_MANAGE` or
#: `AUDIT_READ` — §25 of the specification is explicit that a police account
#: must not be able to make itself an administrator.
_POLICE = _ANALYST | _codes(
    "INVESTIGATION_READ_ASSIGNED",
    "REPORT_READ_ASSIGNED",
)

#: The organisation's administrator. Everything an investigator can do, plus
#: the platform controls — users, roles, the audit trail, erasure, and the
#: threat-intelligence rebuild. Scoped to their own organisation by the
#: repository layer, not by this set.
_ADMIN = _POLICE | _codes(
    "INVESTIGATION_DELETE",
    "USER_MANAGE",
    "ROLE_MANAGE",
    "AUDIT_READ",
    "AGENT_CONFIG",
    "THREAT_INTEL_MANAGE",
    "RESEARCH_READ",
)

#: The platform superadmin. Admin plus the ability to create organisations and
#: see across them.
_OWNER = _ADMIN | _codes("ORG_MANAGE")


#: role name -> the complete set of permission codes it holds.
ROLE_PERMISSIONS: Dict[str, FrozenSet[str]] = {
    "citizen": _CITIZEN,
    "viewer": _VIEWER,
    "researcher": _RESEARCHER,
    "analyst": _ANALYST,
    "police": _POLICE,
    "admin": _ADMIN,
    "owner": _OWNER,
}

#: One sentence per role, seeded into the `roles` table and served to the UI so
#: role copy is not written twice in two languages.
ROLE_DESCRIPTIONS: Dict[str, str] = {
    "citizen": "A member of the public. Investigates what happened to them, and "
               "sees only their own cases.",
    "viewer": "Read-only desk. Sees the organisation's cases and the fraud "
              "intelligence, and changes nothing.",
    "researcher": "Academic access. Aggregated fraud trends, model evaluation "
                  "and anonymised statistics — never a citizen's case.",
    "analyst": "Fraud analyst. Submits investigations, saves case files, works "
               "the intelligence console.",
    "police": "Authorised investigator. Everything an analyst can do, plus the "
              "cases assigned to them.",
    "admin": "Organisation administrator. Users, roles, audit log, erasure and "
             "system configuration.",
    "owner": "Platform owner. Administers organisations themselves and sees "
             "across them.",
}

#: What a role's landing surface is, served on `/api/auth/me` so the client does
#: not hard-code a role -> route table of its own. §23 of the specification.
ROLE_HOME: Dict[str, str] = {
    "citizen": "/dashboard",
    "viewer": "/dashboard",
    "researcher": "/research/dashboard",
    "analyst": "/dashboard",
    "police": "/police/dashboard",
    "admin": "/admin/dashboard",
    "owner": "/admin/dashboard",
}


# ---------------------------------------------------------------------------
# The ladder — retained, and narrowed to what is genuinely ordinal
# ---------------------------------------------------------------------------

#: Ordered least- to most-privileged, and used for exactly two things now:
#: `require_role`'s legacy gate, and the escalation guard that stops an admin
#: minting an owner. The four inherited roles keep their original relative
#: order, so every check written against them answers as it always did.
#:
#: `citizen` and `researcher` sit at rank 0 because they must not pass a
#: `require_role("viewer")` gate — neither may read the organisation's cases.
#: `police` shares rank 2 with `analyst`: they are peers with different
#: permission sets, which is precisely the thing a ladder cannot say and
#: `ROLE_PERMISSIONS` above says instead.
ROLE_RANK: Dict[str, int] = {
    "citizen": 0,
    "researcher": 0,
    "viewer": 1,
    "analyst": 2,
    "police": 2,
    "admin": 3,
    "owner": 4,
}

#: Every role name, in ladder order then alphabetically. `models_db.ROLES`
#: re-exports this so the existing import site keeps working.
ROLES: Tuple[str, ...] = tuple(
    sorted(ROLE_PERMISSIONS, key=lambda r: (ROLE_RANK[r], r))
)

#: The role a public sign-up gets, always. §19: a role is never taken from the
#: sign-up form, because a dropdown that mints administrators is not a feature.
DEFAULT_SIGNUP_ROLE = "citizen"

#: The role `create_user` falls back to when given something unknown. Kept as
#: `viewer` rather than `citizen`: this is the *administrative* create path, and
#: silently downgrading a mistyped role to the least-privileged org member is
#: the same behaviour it has always had.
DEFAULT_ROLE = "viewer"


def permissions_for(role: str) -> FrozenSet[str]:
    """Every permission code `role` holds. Unknown roles hold nothing.

    An unknown role returning the empty set rather than raising is deliberate:
    a database row carrying a role this build does not know about should lock
    that account out of everything, not 500 every request it makes.
    """
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: str, code: str) -> bool:
    return code in permissions_for(role)


def outranks(actor_role: str, target_role: str) -> bool:
    """Whether `actor_role` sits strictly above `target_role` on the ladder.

    The escalation guard. An admin may create an analyst and may not create an
    owner; nobody may promote someone to a role at or above their own.
    """
    return ROLE_RANK.get(actor_role, -1) > ROLE_RANK.get(target_role, 99)


# --- integrity, checked at import ------------------------------------------

_granted = {code for codes in ROLE_PERMISSIONS.values() for code in codes}
_unknown = _granted - set(PERMISSIONS)
if _unknown:  # pragma: no cover - a typo here fails at startup, by design
    raise ImportError(f"ROLE_PERMISSIONS grants unknown permission(s): {sorted(_unknown)}")
_ungranted = set(PERMISSIONS) - _granted
if _ungranted:  # pragma: no cover - same
    raise ImportError(
        f"permission(s) defined but granted to nobody: {sorted(_ungranted)}. "
        "Grant them to a role or delete them — a permission no role holds is a "
        "route nobody can reach."
    )
if set(ROLE_PERMISSIONS) != set(ROLE_RANK) or set(ROLE_PERMISSIONS) != set(ROLE_DESCRIPTIONS):
    raise ImportError(  # pragma: no cover - same
        "ROLE_PERMISSIONS, ROLE_RANK and ROLE_DESCRIPTIONS must describe the same roles"
    )


__all__ = [
    "DEFAULT_ROLE",
    "DEFAULT_SIGNUP_ROLE",
    "PERMISSIONS",
    "ROLES",
    "ROLE_DESCRIPTIONS",
    "ROLE_HOME",
    "ROLE_PERMISSIONS",
    "ROLE_RANK",
    "has_permission",
    "outranks",
    "permissions_for",
]
