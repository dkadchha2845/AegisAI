#!/usr/bin/env bash
# Copy the contract into the web app. schema/ stays the single source of
# truth; these copies are generated and must never be edited by hand.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WEB="$ROOT/apps/web/src"

mkdir -p "$WEB/types" "$WEB/mock"
{ echo "// GENERATED — do not edit. Source: schema/types.ts"
  echo "// Regenerate: ./scripts/sync-contract.sh"
  cat "$ROOT/schema/types.ts"
} > "$WEB/types/contract.ts"
cp "$ROOT/schema/mock-stream.json" "$WEB/mock/stream.json"
echo "synced contract -> apps/web/src/{types,mock}"
