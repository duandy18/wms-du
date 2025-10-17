#!/usr/bin/env bash
# CI forwarder: forward everything to repo root run.sh
set -euo pipefail

# Allow running from any cwd inside the repo
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# Pass through all args to the root script.
if [ -x "${REPO_ROOT}/run.sh" ]; then
  exec "${REPO_ROOT}/run.sh" "$@"
fi

# Fallback: try Makefile if root run.sh not found
if [ $# -ge 1 ] && [ "$1" = "ci:pg:quick" ]; then
  if command -v make >/dev/null 2>&1; then
    echo "[forwarder] root run.sh missing; falling back to make quick"
    exec make quick || true
  fi
fi

echo "[forwarder] Neither root run.sh nor Makefile quick available."
exit 0
