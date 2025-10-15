#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

# run PG container if not running
if ! docker ps --format '{{.Names}}' | grep -q '^wms-db$'; then
  docker run -d --name wms-db \
    -e POSTGRES_USER=wms -e POSTGRES_PASSWORD=wms -e POSTGRES_DB=wms \
    -p 5432:5432 postgres:14-alpine
fi

python3.12 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
python -m pip install -U pip
pip install -e ".[pg,dev]"

export DATABASE_URL="postgresql+psycopg://wms:wms@127.0.0.1:5432/wms"
unset WMS_SQLITE_GUARD
export PYTHONPATH="$PWD"

alembic upgrade head
pytest -q --maxfail=1 --disable-warnings || true

echo "✅ dev-pg ready. try: uvicorn app.main:app --reload"
