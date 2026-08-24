#!/usr/bin/env bash
# Copy the contract into the web app, and regenerate what is derived from it.
# schema/ stays the single source of truth; these copies are generated and must
# never be edited by hand.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WEB="$ROOT/apps/web/src"
PY="${PY:-$ROOT/.venv/bin/python}"

mkdir -p "$WEB/types" "$WEB/mock"
{ echo "// GENERATED — do not edit. Source: schema/types.ts"
  echo "// Regenerate: ./scripts/sync-contract.sh"
  cat "$ROOT/schema/types.ts"
} > "$WEB/types/contract.ts"
cp "$ROOT/schema/mock-stream.json" "$WEB/mock/stream.json"

# The investigation fixture is generated, not copied: it is one InvestigationState
# serialised by Pydantic and annotated with the TypeScript type, so that
# `npm run typecheck` fails on field-level drift the enum check cannot see.
# check_contract.py re-runs this generator in memory and fails if the committed
# output differs, so forgetting to run this script is a gate failure, not a
# silent drift.
"$PY" "$ROOT/schema/mock_investigation.py" >/dev/null
cp "$ROOT/schema/mock-investigation.json" "$WEB/mock/investigation.json"

echo "synced contract -> apps/web/src/{types,mock}"
