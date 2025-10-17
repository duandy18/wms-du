#!/usr/bin/env bash
set -euo pipefail
export DATABASE_URL=${DATABASE_URL:-"postgresql+psycopg://wms:wms@127.0.0.1:5433/wms"}

echo "== migrate =="
if [ -f ./alembic.ini ] || [ -d app/db/migrations ]; then
  alembic upgrade head || true
fi
echo "== quick snapshot =="
pytest -q -s tests/quick/test_snapshot_inventory_pg.py || true
echo "== quick stock query =="
pytest -q -s tests/quick/test_stock_query_pg.py || true
echo "== quick outbound atomic (non-blocking) =="
OUTBOUND_ATOMIC=true pytest -q -s tests/quick/test_outbound_atomic_pg.py || true
echo "All done (non-blocking)."
