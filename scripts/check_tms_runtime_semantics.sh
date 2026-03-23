#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "===== anti-regression: TMS pricing runtime semantics ====="

FORBIDDEN_PATTERN='\bcan_bind\b|compute_template_runtime_status|compute_is_template_active|template_archived|status not draft|template not quotable'

if rg -n \
  -g '!alembic/**' \
  -g '!**/__pycache__/**' \
  -g '!*.pyc' \
  "${FORBIDDEN_PATTERN}" \
  app tests
then
  echo
  echo "ERROR: forbidden old runtime semantics found."
  exit 1
fi

echo "OK: no forbidden old runtime semantics found."
