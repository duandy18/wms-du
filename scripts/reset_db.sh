#!/usr/bin/env bash
set -euo pipefail
rm -f dev.db test.db
alembic upgrade head
python scripts/smoke.py
