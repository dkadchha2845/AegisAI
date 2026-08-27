"""
`make db-shell` — open a SQL console on whatever `DATABASE_URL` names.

One command instead of "remember whether this checkout is on SQLite or the
compose Postgres, then remember that database's client's flags". It reads the
configured URL, picks `sqlite3` or `psql`, and execs it.

It **never prints the URL**, because a Postgres URL carries a password and a
terminal is a place people screenshot. It prints the engine, the host and the
database name — enough to know which database you are about to be in.

If the client binary is missing it says which one to install rather than failing
with `No such file or directory`. See `docs/AUTH.md` for the pgAdmin route,
which is the same database through a browser.
"""

from __future__ import annotations

import os
import shutil
import sys
from urllib.parse import urlsplit

from .config import settings


def main() -> int:
    url = settings.database_url
    if not url:
        print(
            "DATABASE_URL is not set, so there is no durable database to open — "
            "the zero-setup default is a per-process temp file that is deleted "
            "when the API exits.\n"
            "Set one first, e.g.:\n"
            "  export DATABASE_URL=sqlite:///aegis.db\n"
            "  export DATABASE_URL=postgresql+psycopg://aegis:aegis_dev_only@127.0.0.1/aegis",
            file=sys.stderr,
        )
        return 1

    parts = urlsplit(url)
    scheme = parts.scheme.split("+")[0]

    if scheme == "sqlite":
        path = url.split("///", 1)[-1]
        if not shutil.which("sqlite3"):
            print("sqlite3 is not on PATH. `brew install sqlite` / `apt install sqlite3`.",
                  file=sys.stderr)
            return 1
        print(f"sqlite → {path}")
        print("  .tables            list tables")
        print("  .schema users      the users table's DDL")
        print("  .quit              leave")
        os.execvp("sqlite3", ["sqlite3", path])  # noqa: S606

    if scheme in ("postgresql", "postgres"):
        if not shutil.which("psql"):
            print("psql is not on PATH. `brew install libpq` / `apt install postgresql-client`.",
                  file=sys.stderr)
            return 1
        # psql understands a libpq URL; hand it the original minus the SQLAlchemy
        # driver suffix. Printed *without* it — the URL carries a password.
        print(f"postgres → {parts.hostname}:{parts.port or 5432}{parts.path}")
        print("  \\dt        list tables")
        print("  \\d users   describe the users table")
        print("  \\q         leave")
        os.execvp("psql", ["psql", f"{scheme}://{parts.netloc}{parts.path}"])  # noqa: S606

    print(f"No console wired up for a {scheme!r} URL — open it with that engine's own client.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
