#!/usr/bin/env bash
set -Eeuo pipefail
# Always delegate to the single source of truth in repo root.
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || dirname "$(dirname "$(readlink -f "$0")")")"
exec "$ROOT/run.sh" "$@"
