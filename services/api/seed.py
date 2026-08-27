"""
Development seed and credential CLI.

    .venv/bin/python -m services.api.seed seed
    .venv/bin/python -m services.api.seed users
    .venv/bin/python -m services.api.seed set-password citizen@aegis.local
    .venv/bin/python -m services.api.seed promote someone@org.gov.in analyst

Or through the Makefile: `make seed`, `make users`, `make set-password EMAIL=…`.

**Why a CLI and not a fixture file.** §15 asks that demo passwords not be
written into source, and §37 that seeding be idempotent. Both fall out of using
the same `auth.seed_admin()` the API calls at boot: there is one seed, it is
reconciling rather than inserting, and running it twice is a no-op. The
passwords come from configuration (`AEGIS_DEMO_PASSWORD`,
`AEGIS_ADMIN_PASSWORD`), so changing them is a environment change, not a patch.

**`set-password` is the documented answer to "I forgot the demo password".** It
generates a strong one, prints it once, and revokes every session that account
holds — which is what a real credential reset has to do. It is a shell command
rather than an endpoint on purpose: the ability to set anyone's password from a
terminal is exactly the ability that must not be reachable over HTTP.

**This writes to `DATABASE_URL`.** With none set, `db.py` invents a per-process
temp file that is deleted when this process exits, so seeding it would be a
command that reports success and changes nothing — the same trap `migrations/
env.py` refuses for `alembic upgrade`. This refuses it the same way, with the
same explanation.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from typing import Optional

from . import db as db_mod
from .auth import (
    DEMO_ROSTER,
    create_user,
    demo_password,
    get_user_by_email,
    hash_password,
    revoke_all_sessions,
    seed_admin,
    seed_rbac,
    set_user_role,
)
from .config import settings
from .db import SessionLocal, init_db
from .models_db import ROLES, Organization, User


def _require_durable() -> None:
    if db_mod.EPHEMERAL:
        sys.exit(
            "DATABASE_URL is not set, so this would seed the per-process temp "
            "database that is deleted when this command exits — a no-op that "
            "reports success.\n"
            "Set one first, e.g.:\n"
            "  export DATABASE_URL=sqlite:///aegis.db\n"
            "  export DATABASE_URL=postgresql+psycopg://aegis:aegis_dev_only@127.0.0.1/aegis"
        )


def cmd_seed(_args: argparse.Namespace) -> int:
    """Roles, permissions, the default organisation, the owner, and — in open
    mode — the demo roster. Idempotent: run it as often as you like."""
    _require_durable()
    init_db()
    db = SessionLocal()
    try:
        seed_admin(db)
        roles = {u.role for u in db.query(User).all()}
        print(
            f"seeded. users={db.query(User).count()} "
            f"orgs={db.query(Organization).count()} roles_in_use={sorted(roles)}"
        )
        if not settings.auth_enforced:
            print(
                f"demo accounts share the password {demo_password()!r} "
                "(AEGIS_DEMO_PASSWORD); none of them are created when AEGIS_AUTH=1."
            )
    finally:
        db.close()
    return 0


def cmd_users(_args: argparse.Namespace) -> int:
    """The roster, with roles. Never prints a hash — there is no reason to look
    at one, and a command that prints them is a command someone pipes to a file."""
    db = SessionLocal()
    try:
        rows = db.query(User).order_by(User.id.asc()).all()
        if not rows:
            print("no users. Run `python -m services.api.seed seed` first.")
            return 0
        width = max(len(u.email) for u in rows)
        print(f"{'#':>4}  {'email'.ljust(width)}  {'role':<11} {'org':<5} status")
        for u in rows:
            status = "disabled" if u.disabled else "active"
            print(
                f"{u.id:>4}  {u.email.ljust(width)}  {u.role:<11} "
                f"{u.org_id or '-'!s:<5} {status}"
            )
        demo = {email for email, _r, _o, _n in DEMO_ROSTER}
        seeded = [u.email for u in rows if u.email in demo]
        if seeded and not settings.auth_enforced:
            print(
                f"\n{len(seeded)} seeded demo account(s) share the password "
                f"{demo_password()!r} (AEGIS_DEMO_PASSWORD)."
            )
    finally:
        db.close()
    return 0


def cmd_set_password(args: argparse.Namespace) -> int:
    """Set a password and end every session that account holds.

    Prints the new password once. That is the point of the command — it is the
    documented recovery path when a development credential is lost — and it is
    why it lives in a terminal rather than behind a route.
    """
    _require_durable()
    db = SessionLocal()
    try:
        user = get_user_by_email(db, args.email)
        if user is None:
            print(f"no account {args.email!r}", file=sys.stderr)
            return 1
        password: Optional[str] = args.password or None
        if password is None:
            # Three words' worth of entropy, readable enough to retype once.
            password = f"aegis-{secrets.token_urlsafe(9)}"
        user.password_hash = hash_password(password)
        db.commit()
        revoked = revoke_all_sessions(db, user.id)
        print(f"{user.email}: password set; {revoked} session(s) revoked")
        print(f"  password: {password}")
        print("  (shown once — it is stored only as a hash)")
    finally:
        db.close()
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    """Change an account's role from the terminal.

    The API's own escalation guard refuses to grant a role at or above the
    caller's, which is correct over HTTP and unhelpful when there is no owner to
    ask. Shell access to the database is already total authority, so this does
    not pretend otherwise — it revokes the account's sessions so the new role
    takes effect on the next sign-in rather than whenever the old token expires.
    """
    _require_durable()
    if args.role not in ROLES:
        print(f"role must be one of {', '.join(ROLES)}", file=sys.stderr)
        return 1
    db = SessionLocal()
    try:
        seed_rbac(db)  # the roles table must exist before role_id can be set
        user = get_user_by_email(db, args.email)
        if user is None:
            print(f"no account {args.email!r}", file=sys.stderr)
            return 1
        was = user.role
        set_user_role(db, user, args.role)
        db.commit()
        revoked = revoke_all_sessions(db, user.id)
        print(f"{user.email}: {was} -> {user.role}; {revoked} session(s) revoked")
    finally:
        db.close()
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    """Provision one account. For the first administrator on a fresh enforced
    deployment, where there is nobody to sign in as yet."""
    _require_durable()
    if args.role not in ROLES:
        print(f"role must be one of {', '.join(ROLES)}", file=sys.stderr)
        return 1
    init_db()
    db = SessionLocal()
    try:
        seed_rbac(db)
        if get_user_by_email(db, args.email) is not None:
            print(f"{args.email} already exists — use set-password or promote", file=sys.stderr)
            return 1
        from .orgs import get_or_create_default_org

        password = args.password or f"aegis-{secrets.token_urlsafe(9)}"
        user = create_user(
            db, args.email, password, role=args.role,
            org_id=get_or_create_default_org(db).id, full_name=args.name,
        )
        print(f"created {user.email} as {user.role}")
        if not args.password:
            print(f"  password: {password}")
            print("  (shown once — it is stored only as a hash)")
    finally:
        db.close()
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m services.api.seed",
        description="AegisAI development seed and credential tool.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("seed", help="roles, permissions, default org, owner, demo roster").set_defaults(
        func=cmd_seed
    )
    sub.add_parser("users", help="list accounts and their roles").set_defaults(func=cmd_users)

    sp = sub.add_parser("set-password", help="set an account's password and end its sessions")
    sp.add_argument("email")
    sp.add_argument("--password", help="use this instead of a generated one")
    sp.set_defaults(func=cmd_set_password)

    pr = sub.add_parser("promote", help="change an account's role")
    pr.add_argument("email")
    pr.add_argument("role", choices=list(ROLES))
    pr.set_defaults(func=cmd_promote)

    cr = sub.add_parser("create", help="provision one account")
    cr.add_argument("email")
    cr.add_argument("role", choices=list(ROLES))
    cr.add_argument("--name", default=None)
    cr.add_argument("--password", help="use this instead of a generated one")
    cr.set_defaults(func=cmd_create)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
