#!/usr/bin/env bash
# Start a dev server from this checkout — the main one or a git worktree.
#
#   scripts/dev.sh api    FastAPI on :8000 (reload-dir set, so reloads keep the DB)
#   scripts/dev.sh web    Vite on :5173
#
# Why this exists (audit B-06): `.claude/launch.json` used to run
# `.venv/bin/python` and `npm --prefix apps/web` relative to the checkout, and a
# git worktree has neither a `.venv` nor `apps/web/node_modules` — they are
# gitignored, so only the primary checkout holds them. Starting the API from a
# worktree therefore failed. This script runs *this* checkout's code, using its
# own environments when it has them and the primary checkout's when it does not.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"

# The primary checkout is the parent of the shared .git directory. For the
# primary checkout itself that is just `$here`.
primary="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)"

venv_python() {
  for root in "$here" "$primary"; do
    if [ -x "$root/.venv/bin/python" ]; then echo "$root/.venv/bin/python"; return; fi
  done
  echo "no .venv in $here or $primary — run \`make install\` in the primary checkout" >&2
  exit 1
}

case "${1:-}" in
  api)
    exec "$(venv_python)" -m uvicorn services.api.main:app --reload \
      --reload-dir services --reload-dir schema --port "${PORT:-8000}"
    ;;
  web)
    if [ ! -d apps/web/node_modules ]; then
      if [ -d "$primary/apps/web/node_modules" ]; then
        # A symlink, not a copy: node_modules is gitignored, so this never
        # enters a commit, and the worktree picks up the primary's installs.
        ln -s "$primary/apps/web/node_modules" apps/web/node_modules
      else
        echo "no apps/web/node_modules here or in $primary — run \`npm ci --prefix apps/web\`" >&2
        exit 1
      fi
    fi
    exec npm run dev --prefix apps/web
    ;;
  *)
    echo "usage: scripts/dev.sh api|web" >&2
    exit 2
    ;;
esac
