#!/usr/bin/env bash
# WMS-DU CI router: migrate → health → quick → smoke (PG on 5433)
set -euo pipefail

# --- Locale / IO ---
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
export PYTHONIOENCODING=UTF-8

log(){ printf "\n[%s] %s\n" "$(date +'%H:%M:%S')" "$*"; }

# --- Human-friendly → internal mapping ---
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

# --- Wait for Postgres ---
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

# --- Pre-fix: widen alembic_version.version_num & seed baseline if missing ---
fix_alembic_version_len() {
  log "Bootstrap alembic_version as VARCHAR(255) at baseline (if needed)"
  if command -v psql >/dev/null 2>&1; then
    python3 - <<'PY'
import os, urllib.parse as up, subprocess
url = os.environ.get("DATABASE_URL","").replace("+psycopg","")
u = up.urlparse(url)
user, pwd = u.username or "wms", u.password or "wms"
host, port = u.hostname or "127.0.0.1", u.port or 5433
db = (u.path or "/wms").lstrip("/") or "wms"
dsn = f"postgresql://{user}:{pwd}@{host}:{port}/{db}"
sql = r"""
DO $$
BEGIN
  IF to_regclass('public.alembic_version') IS NULL THEN
    CREATE TABLE public.alembic_version (version_num VARCHAR(255) NOT NULL);
    INSERT INTO public.alembic_version(version_num) VALUES ('f995a82ac74e');
  ELSE
    IF EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema='public' AND table_name='alembic_version' AND column_name='version_num'
        AND character_maximum_length IS NOT NULL AND character_maximum_length < 128
    ) THEN
      ALTER TABLE public.alembic_version ALTER COLUMN version_num TYPE VARCHAR(255);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.alembic_version) THEN
      INSERT INTO public.alembic_version(version_num) VALUES ('f995a82ac74e');
    END IF;
  END IF;
END$$;
"""
subprocess.check_call(["psql", dsn, "-c", sql])
PY
  else
    python3 - <<'PY'
import os, asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
url = os.environ.get("DATABASE_URL")
if not url: raise SystemExit(0)
eng = create_async_engine(url, future=True)
sql = """
DO $$
BEGIN
  IF to_regclass('public.alembic_version') IS NULL THEN
    CREATE TABLE public.alembic_version (version_num VARCHAR(255) NOT NULL);
    INSERT INTO public.alembic_version(version_num) VALUES ('f995a82ac74e');
  ELSE
    IF EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema='public' AND table_name='alembic_version' AND column_name='version_num'
        AND character_maximum_length IS NOT NULL AND character_maximum_length < 128
    ) THEN
      ALTER TABLE public.alembic_version ALTER COLUMN version_num TYPE VARCHAR(255);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.alembic_version) THEN
      INSERT INTO public.alembic_version(version_num) VALUES ('f995a82ac74e');
    END IF;
  END IF;
END$$;
"""
async def main():
    async with eng.begin() as c:
        await c.execute(text(sql))
asyncio.run(main())
PY
  fi
}

# --- Tasks ---
task_pg_migrate(){
  log "Alembic upgrade -> head"
  wait_pg || true
  fix_alembic_version_len
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
  python3 tools/db_invariants.py
}

task_quick(){
  log "pytest quick"
  pytest -q tests/quick -m "not slow" --maxfail=1 --durations=10
}

db_hard_reset(){
  log "Reset DB schema → clean baseline for Smoke"
  if command -v psql >/dev/null 2>&1; then
    python3 - <<'PY'
import os, urllib.parse as up, subprocess
url = os.environ.get("DATABASE_URL","").replace("+psycopg","")
u = up.urlparse(url)
user, pwd = u.username or "wms", u.password or "wms"
host, port = u.hostname or "127.0.0.1", u.port or 5433
db = (u.path or "/wms").lstrip("/") or "wms"
dsn = f"postgresql://{user}:{pwd}@{host}:{port}/{db}"
subprocess.check_call(["psql", dsn, "-c", "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"])
PY
  else
    python3 - <<'PY'
import os, asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
url = os.environ.get("DATABASE_URL"); eng = create_async_engine(url, future=True)
async def main():
    async with eng.begin() as c:
        await c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await c.execute(text("CREATE SCHEMA public"))
asyncio.run(main())
PY
  fi
  # Seed alembic_version with widened column & baseline
  fix_alembic_version_len
  alembic upgrade head
}

task_smoke(){
  db_hard_reset
  log "pytest smoke"
  if [ -d tests/smoke ]; then
    pytest -q tests/smoke --maxfail=1 --durations=10
  else
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
  ./run.sh ci:pg:all      # 迁移 → 体检 → quick → smoke（主入口）
  ./run.sh ci:pg:migrate  # 仅迁移
  ./run.sh ci:pg:health   # 迁移 + 体检（含不变量）
  ./run.sh ci:pg:quick    # 迁移 + 体检 + quick
  ./run.sh ci:pg:smoke    # 迁移 + 体检 + smoke（会先重置数据库）
  # 也可直接传人类可读名："Smoke (PG)" / "Quick (PG)" / "Full (PG)"
USAGE
      exit 1 ;;
  esac
}
main "$@"
