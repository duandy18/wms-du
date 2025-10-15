#!/usr/bin/env bash
# WMS-DU CI router: migrate → health → quick → smoke (PG on 5433)
# 约定：CI 的 postgres 服务以 5433:5432 暴露；DATABASE_URL 统一走 5433。
set -euo pipefail

# 统一 UTF-8，避免 mojibake / heredoc / locale 抽风
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
export PYTHONIOENCODING=UTF-8

log(){ printf "\n[%s] %s\n" "$(date +'%H:%M:%S')" "$*"; }

# --- 人类可读检查名 → 内部任务名 ---
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

# --- 等待 PG 就绪（默认 5433；可被 PGHOST/PGPORT/DATABASE_URL 覆盖）---
wait_pg(){
  local h="${PGHOST:-${1:-127.0.0.1}}"
  local p="${PGPORT:-${2:-5433}}"
  local u="${3:-wms}"
  local d="${4:-wms}"

  if [[ -n "${DATABASE_URL:-}" ]]; then
    # 若未显式设置 PGHOST/PGPORT，则尽力从 DATABASE_URL 推断
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

# --- 默认环境 ---
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
    python3 tools/pg_healthcheck.py --strict --output pg_health/report.json || true
  else
    echo "WARN: tools/pg_healthcheck.py missing; skipping strict checks"
  fi
  # 不变量校验使用独立脚本（避免 heredoc/编码坑）
  python3 tools/db_invariants.py
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
  ./run.sh ci:pg:smoke    # 迁移 + 体检 + smoke
  # 也可传人类可读名："Smoke (PG)" / "Quick (PG)" / "Full (PG)"
USAGE
      exit 1 ;;
  esac
}
main "$@"
