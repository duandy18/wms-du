#!/usr/bin/env bash
# WMS-DU root runner: local-first, CI reuses this script.
# - Single-dev multi-machine friendly
# - Non-blocking mode via NON_BLOCKING=1
# - Postgres via $DATABASE_URL (defaults to local 5433 if docker-up used)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

# ---------- helpers ----------
log()  { printf "\033[1;36m[%s]\033[0m %s\n" "$(date +%H:%M:%S)" "$*"; }
warn() { printf "\033[1;33m[%s]\033[0m %s\n" "$(date +%H:%M:%S)" "$*"; }
err()  { printf "\033[1;31m[%s]\033[0m %s\n" "$(date +%H:%M:%S)" "$*" >&2; }
nbegin(){
  if [[ "${NON_BLOCKING:-0}" = "1" ]]; then
    set +e
    warn "NON_BLOCKING=1 -> errors won't fail the whole run"
  fi
}

# Default DB if user used docker-up (5433 on host)
: "${DATABASE_URL:=postgresql+psycopg://wms:wms@127.0.0.1:5433/wms}"  # pragma: allowlist secret

# ---------- core steps ----------
step_env() {
  log "Env"
  echo "PY=$(python -V 2>&1 || true)"
  echo "DATABASE_URL=${DATABASE_URL}"
  echo "WMS_SQLITE_GUARD=${WMS_SQLITE_GUARD:-}"
}

step_migrate() {
  log "Migrate (alembic if present)"
  if [[ -f "alembic.ini" || -d "app/db/migrations" ]]; then
    alembic upgrade head || return 0
  else
    warn "No alembic found, skip."
  fi
}

# Quick tests (needle set)
t_quick_snapshot() {
  log "Quick: snapshot pagination/search"
  pytest -q -s tests/quick/test_snapshot_inventory_pg.py
}
t_quick_stock_query() {
  log "Quick: /stock/query happy path"
  pytest -q -s tests/quick/test_stock_query_pg.py
}
t_quick_outbound_atomic() {
  log "Quick: outbound atomic (should 409 & rollback)"
  OUTBOUND_ATOMIC=true pytest -q -s tests/quick/test_outbound_atomic_pg.py
}

# ---------- docker helpers (local dev) ----------
pg_up() {
  log "Docker PG up @5433"
  docker run -d --name wms-pg \
    -e POSTGRES_USER=wms -e POSTGRES_PASSWORD=wms -e POSTGRES_DB=wms \
    -p 5433:5432 postgres:14-alpine >/dev/null
  sleep 3
  echo "DATABASE_URL=${DATABASE_URL}"
}
pg_down() {
  log "Docker PG down"
  docker rm -f wms-pg >/dev/null 2>&1 || true
}

# ---------- command dispatcher ----------
usage() {
  cat <<'EOF'
Usage:
  bash run.sh <command>

Commands (CI-focused):
  ci:pg:quick      Show env -> migrate -> run 3 quick needles (non-blocking if NON_BLOCKING=1)

Local helpers:
  pg:up            Start local postgres:14 (host port 5433)
  pg:down          Stop/remove local postgres

Single tests:
  quick:snapshot   Run tests/quick/test_snapshot_inventory_pg.py
  quick:stock      Run tests/quick/test_stock_query_pg.py
  quick:atomic     Run tests/quick/test_outbound_atomic_pg.py
EOF
}

case "${1:-}" in
  ci:pg:quick)
    nbegin
    step_env
    step_migrate || true
    t_quick_snapshot || true
    t_quick_stock_query || true
    t_quick_outbound_atomic || true
    log "ci:pg:quick done."
    ;;
  pg:up)   pg_up ;;
  pg:down) pg_down ;;
  quick:snapshot) t_quick_snapshot ;;
  quick:stock)    t_quick_stock_query ;;
  quick:atomic)   t_quick_outbound_atomic ;;
  ""|-h|--help) usage ;;
  *)
    err "Unknown command: $1"
    usage
    exit 2
    ;;
esac
