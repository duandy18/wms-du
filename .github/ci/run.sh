#!/usr/bin/env bash
set -Eeuo pipefail
# 始终转发到仓库根目录的 run.sh，确保单一真源
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "$(cd "$(dirname "$0")/../.." && pwd)")"
exec "$ROOT/run.sh" "$@"
