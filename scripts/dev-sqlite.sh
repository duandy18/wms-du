#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

python3.12 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
python -m pip install -U pip
pip install -e ".[pg,dev]"

export PYTHONPATH="$PWD"
export WMS_SQLITE_GUARD=1
pytest -q --maxfail=1 --disable-warnings || true

echo "✅ dev-sqlite ready. try: uvicorn app.main:app --reload"
