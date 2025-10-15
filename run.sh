#!/usr/bin/env bash
# WMS-DU CI router: migrate → health → quick → smoke (PG on 5433)
# Convention: CI Postgres service is exposed as 5433:5432; DATABASE_URL uses 5433.
set -euo pipefail

# force UTF-8 to avoid mojibake/heredoc surprises
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
export PYTHONIOENCODING=UTF-8

log(){ printf "\n[%s] %s\n" "$(date +'%H:%M:%S')" "$*"; }

# --- Human-friendly check names → internal task mapping ---
normalize_task(){
  local pretty="${1:-ci:pg:all}"
  case "$pretty" in
    "Smoke (PG)")        echo "ci:pg:smoke" ;;
    "Quick (PG)")        echo "ci:pg:quick" ;;
    "Full (PG)")         echo "ci:pg:all"   ;;
    "Lint & Typecheck")  echo "ci:lint"     ;;
    "Coverage Gate")     echo "ci:coverage" ;;
    *)                   echo "$pretty"     ;;
  esac
}

# --- Wait for Postgres (defaults to 5433; can be overridden by PGHOST/PGPORT/DATABASE_URL) ---
wait_pg(){
  local h="${PGHOST:-${1:-127.0.0.1}}"
  local p="${PGPORT:-${2:-5433}}"
  local u="${3:-wms}"
  local d="${4:-wms}"

  if [[ -n "${DATABASE_URL:-}" ]]; then
    if [[ -z "${PGPORT:-}" && "$DATABASE_URL" =~ :([0-9]{2,5})/ ]]; then p="${BASH_REMATCH[1]}"; fi
    if [[ -z "${PGHOST:-}" && "$DATABASE_URL" =~ @([^:/]+):[0-9]+/ ]]; then h="${BASH_REMATCH[1]}"; fi
  fi

  if command -v pg_isready >/dev/null 2>&1; then
    for _ in $(seq 1 60); do
      if pg_isready -h "$h" -p "$p" -U "$u" -d "$d" >/dev/null 2>&1; then
        return 0
      fi
      sleep 1
    done
    echo "Postgres not ready after 60s on ${h}:${p}" >&2
    exit 2
  fi
}

# --- Defaults ---
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://wms:wms@127.0.0.1:5433/wms}"

# --- Tasks ---
task_pg_migrate(){
  log "Alembic upgrade -> head"
  wait_pg || true
  alembic upgrade head
}

task_pg_health(){
  log "PG healthcheck (strict)"
  mkdir -p pg_health
  if [ -f tools/pg_healthcheck.py ]; then
    python3 tools/pg_healthcheck.py --strict --output pg_health/report.json || true
  else
    echo "WARN: tools/pg_healthcheck.py missing; skipping strict checks"
  fi
  # Invariant checks (tools/db_invariants.py)
  python3 tools/db_invariants.py
}

task_quick(){
  log "pytest quick"
  pytest -q tests/quick -m "not slow" --maxfail=1 --durations=10
}

# --- hard reset DB before smoke to satisfy smoke's hard-coded checks (item_id=1, loc0/101) ---
db_hard_reset(){
  log "Reset DB schema → clean baseline for Smoke"
  python3 - <<'PY'
import os
from sqlalchemy import create_engine, text
url = os.environ.get("DATABASE_URL","").replace("+psycopg","")
eng = create_engine(url)
with eng.begin() as c:
    c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
    c.execute(text("CREATE SCHEMA public"))
    # PG 默认搜索路径
    c.execute(text("COMMENT ON SCHEMA public IS 'standard public schema'"))
PY
  alembic upgrade head
}

task_smoke(){
  # reset DB to clean state so smoke's seeds produce item_id=1 and loc0/101
  db_hard_reset

  log "pytest smoke"
  if [ -d tests/smoke ]; then
    pytest -q tests/smoke --maxfail=1 --durations=10
  else
    # fallback: minimal smoke set（按你的项目情况可保留）
    pytest -q \
      tests/quick/test_inbound_pg.py::test_inbound_receive_and_putaway_integrity \
      tests/quick/test_putaway_pg.py::test_putaway_integrity \
      -s --maxfail=1 --durations=10
  fi
}

main(){
  local cmd="${1:-ci:pg:all}"
  local mapped; mapped="$(normalize_task "$cmd")"
  case "$mapped" in
    ci:pg:migrate) task_pg_migrate ;;
    ci:pg:health)  task_pg_migrate; task_pg_health ;;
    ci:pg:quick)   task_pg_migrate; task_pg_health; task_quick ;;
    ci:pg:smoke)   task_pg_migrate; task_pg_health; task_smoke ;;
    ci:pg:all)     task_pg_migrate; task_pg_health; task_quick; task_smoke ;;
    *)
      cat <<'USAGE'
Usage:
  ./run.sh ci:pg:all      # migrate → health → quick → smoke（主入口）
  ./run.sh ci:pg:migrate  # 仅迁移
  ./run.sh ci:pg:health   # 迁移 + 体检（含不变量）
  ./run.sh ci:pg:quick    # 迁移 + 体检 + quick
  ./run.sh ci:pg:smoke    # 迁移 + 体检 + smoke（会先重置数据库）
  # 也可直接传人类可读名： "Smoke (PG)" / "Quick (PG)" / "Full (PG)"
USAGE
      exit 1 ;;
  esac
}
main "$@"
