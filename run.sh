#!/usr/bin/env bash
# WMS-DU CI 老路由（转发器落地）：迁移 → 体检 → quick → smoke
# 约定端口：5433（CI 服务用 5433:5432 暴露）
set -euo pipefail

log(){ printf "\n[%s] %s\n" "$(date +'%H:%M:%S')" "$*"; }

# --- 友好检查名 → 旧任务名映射（便于矩阵展示人类可读名称） ---
normalize_task(){
  local pretty="${1:-ci:pg:all}"
  case "$pretty" in
    "Smoke (PG)")        echo "ci:pg:smoke" ;;
    "Quick (PG)")        echo "ci:pg:quick" ;;
    "Full (PG)")         echo "ci:pg:all"   ;;
    "Lint & Typecheck")  echo "ci:lint"     ;;   # 预留
    "Coverage Gate")     echo "ci:coverage" ;;   # 预留
    *)                   echo "$pretty"     ;;
  esac
}

# --- PG 就绪探测：默认 5433，可用 PGHOST/PGPORT/DATABASE_URL 覆盖 ---
wait_pg(){
  local h="${PGHOST:-${1:-127.0.0.1}}"
  local p="${PGPORT:-${2:-5433}}"
  local u="${3:-wms}"
  local d="${4:-wms}"

  if [[ -n "${DATABASE_URL:-}" ]]; then
    # 粗略从 DATABASE_URL 推断 host:port（若未显式指定 PGHOST/PGPORT）
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

# --- 环境变量默认值 ---
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://wms:wms@127.0.0.1:5433/wms}"

# --- 任务实现 ---
task_pg_migrate(){
  log "Alembic upgrade -> head"
  wait_pg || true
  alembic upgrade head
}

task_pg_health(){
  log "PG healthcheck (strict)"
  mkdir -p pg_health
  if [ -f tools/pg_healthcheck.py ]; then
    python tools/pg_healthcheck.py --strict --output pg_health/report.json
  else
    python - <<'PY'
print("WARN: tools/pg_healthcheck.py missing; skipping strict checks")
PY
  fi

  # 关键不变量断言（PostgreSQL）
  python - <<'PY'
import os, sys
from sqlalchemy import create_engine, text
url = os.environ.get("DATABASE_URL", "").replace("+psycopg","")
if not url:
    sys.exit(0)
eng = create_engine(url)
with eng.begin() as c:
    errors = []

    # stocks(item_id, location_id) UNIQUE
    uniques = c.execute(text("""
        SELECT pg_get_constraintdef(c.oid) AS def
        FROM pg_constraint c
        WHERE c.conrelid = 'public.stocks'::regclass
          AND c.contype = 'u'
    """)).fetchall()
    has_uq = any(("UNIQUE (" in r.def and "item_id" in r.def and "location_id" in r.def) for r in uniques)
    if not has_uq:
        errors.append("缺少 stocks(item_id, location_id) 的唯一约束。")

    # stock_ledger.stock_id → stocks.id 外键
    fks = c.execute(text("""
        SELECT pg_get_constraintdef(c.oid) AS def
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_class r ON r.oid = c.confrelid
        WHERE c.contype = 'f'
          AND t.relname = 'stock_ledger'
          AND r.relname = 'stocks'
    """)).fetchall()
    has_fk = any("(stock_id)" in r.def and "REFERENCES public.stocks(id)" in r.def for r in fks)
    if not has_fk:
        errors.append("缺少 stock_ledger(stock_id) → stocks(id) 的外键。")

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        sys.exit(2)
    else:
        print("DB invariants OK: stocks 唯一 + ledger 外键")
PY
}

task_quick(){
  log "pytest quick"
  pytest -q tests/quick -m "not slow" --maxfail=1 --durations=10
}

task_smoke(){
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

# --- 入口 ---
main(){
  local cmd="${1:-ci:pg:all}"
  # 兼容人类友好检查名
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
  ./run.sh ci:pg:all      # 迁移→体检→quick→smoke（主入口）
  ./run.sh ci:pg:migrate  # 仅迁移
  ./run.sh ci:pg:health   # 迁移 + 体检
  ./run.sh ci:pg:quick    # 迁移 + 体检 + quick
  ./run.sh ci:pg:smoke    # 迁移 + 体检 + smoke
  # 也可直接传人类可读名： "Smoke (PG)" / "Quick (PG)" / "Full (PG)"
USAGE
      exit 1 ;;
  esac
}
main "$@"
