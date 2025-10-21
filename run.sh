#!/usr/bin/env bash
# ============================================================
# WMS-DU unified runner (local + CI)
# Single source of truth. Invoked by CI and developers alike.
# ============================================================
set -Eeuo pipefail

# -------- Global env with sane defaults (CI can override) ---
export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"
export PYTHONPATH="${PYTHONPATH:-.}"
export WMS_SQLITE_GUARD="${WMS_SQLITE_GUARD:-1}"
# Local default 5433 (compose maps container 5432→host 5433). CI can export DATABASE_URL explicitly.
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://wms:wms@127.0.0.1:5433/wms}"
export ALEPH="${ALEPH:-alembic.ini}"

# ---- Test suites (keep them centralized here) -------------
QUICK_SUITES=(
  "tests/quick/test_platform_outbound_commit_pg.py -q -s"
  "tests/quick/test_outbound_concurrency_pg.py -q -s"
  "tests/quick/test_new_platforms_pg.py -q -s"
  "tests/quick/test_platform_multi_shop_pg.py -q -s"
)
SMOKE_SUITES=(
  "tests/smoke/test_platform_events_smoke_pg.py -q -s"
)

# ----------------- Helpers --------------------------------
banner() { echo -e "\n\033[1;36m==== $* ====\033[0m\n"; }

# Parse postgres URL (postgresql:// or postgresql+psycopg://)
# Output: <host> <port> <user> <pass> <db>
parse_db_parts() {
  local url="${DATABASE_URL#postgresql://}"
  url="${url#postgresql+psycopg://}"
  local auth hostport db user pass host port
  if [[ "$url" == *"@"* ]]; then
    auth="${url%@*}"
    hostport="${url#*@}"
    user="${auth%%:*}"
    pass="${auth#*:}"
  else
    auth=""
    hostport="$url"
    user="${PGUSER:-wms}"
    pass="${PGPASSWORD:-wms}"
  }
  db="${hostport#*/}"; db="${db%%\?*}"
  host="${hostport%%:*}"
  port="${hostport#*:}"
  [[ "$port" == "$hostport" ]] && port=5432
  echo "$host" "$port" "$user" "$pass" "$db"
}

wait_for_db() {
  local host port user pass db
  read -r host port user pass db < <(parse_db_parts)
  banner "Waiting for PostgreSQL at ${host}:${port}"
  # short warm-up to let container bind port
  sleep 3
  for i in {1..60}; do
    if command -f pg_isready >/dev/null 2>&1; then
      if pg_isready -h "$host" -p "$port" -U "$user" >/dev/null 2>&1; then
        echo "✅ Postgres ready (pg_isready)"
        return 0
      fi
    fi
    if command -v psql >/dev/null 2>&1; then
      PGPASSWORD="$pass" psql "postgresql://${user}:${pass}@${host}:${port}/${db}" -c 'select 1' >/dev/null 2>&1 && {
        echo "✅ Postgres ready (psql)"
        return 0
      }
    fi
    sleep 2
  done
  echo "❌ Timeout waiting for Postgres at ${host}:${port}"
  return 1
}

migrate() {
  banner "Running Alembic migrations (${ALEPH})"
  export ALEMBIC_CONFIG="${ALEPH}"
  alembic upgrade head
}

run_pytest_suites() {
  local -n arr=$1
  for spec in "${arr[@]}"; do
    echo "🧪 pytest ${spec}"
    pytest ${spec}
  done
}

# ----------------- Commands --------------------------------
cmd_env() {
  banner "Environment"
  echo "Python        : $(python -V 2>/dev/null || true)"
  echo "Executable    : $(command -v python || true)"
  echo "PYTHONPATH    : ${PYTHONPATH}"
  echo "DATABASE_URL  : ${DATABASE_URL}"
  echo "WMS_SQLITE_GD : ${WMS_SQLITE_GUARD}"
}

cmd_ci_prepare() { wait_for_db; migrate; }

cmd_test_quick() { banner "Run QUICK suites"; run_pytest_suites QUICK_SUITES; }

cmd_test_smoke() { banner "Run SMOKE suites"; run_pytest_suites SMOKE_SUITES; }

cmd_ci_all() { cmd_env; cmd_ci_prepare; cmd_test_quick; cmd_test_smoke; }

usage() {
  cat <<'USAGE'
Usage: ./run.sh <command>

Commands:
  ci:env            Print environment info
  ci:pg:prepare     Wait for Postgres & run Alembic migrations
  ci:test:quick     Run QUICK (unit + small e2e)
  ci:test:smoke     Run SMOKE (E2E)
  ci:all            env + migrate + quick + smoke

Examples:
  export DATABASE_URL='postgresql+psycopg://wms:wms@127.0.0.1:5433/wms'
  ./run.sh ci:env
  ./run.sh ci:pg:prepare
  ./run.sh ci:test:quick
  ./run.sh ci:test:smoke
  ./run.sh ci:all
USAGE
}

# ----------------- Entrypoint -------------------------------
case "${1:-}" in
  ci:env)          cmd_env ;;
  ci:pg:prepare)   cmd_ci_prepare ;;
  ci:test:quick)   cmd_test_quick ;;
  ci:test:smoke)   cmd_test_smoke ;;
  ci:all)          cmd_ci_all ;;
  *) usage; exit 1 ;;
esac
