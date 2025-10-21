#!/usr/bin/env bash
# ============================================================
# WMS-DU unified runner (local + CI)
# ============================================================
# 用途：
#   - 本地/CI 一致执行
#   - 负责 DB 等待、迁移、quick/smoke 测试、环境打印
# ============================================================

set -Eeuo pipefail

# ------------------ 全局配置 ------------------
export PYTHONUNBUFFERED=${PYTHONUNBUFFERED:-1}
export PYTHONPATH=${PYTHONPATH:-.}
export WMS_SQLITE_GUARD=${WMS_SQLITE_GUARD:-1}
# 本地默认 5433；CI 的 workflow 会把它 override 成 5433（容器 5432->host 5433）
export DATABASE_URL=${DATABASE_URL:-postgresql+psycopg://wms:wms@127.0.0.1:5433/wms}

# Quick 测试集合
QUICK_SUITES=(
  "tests/quick/test_platform_outbound_commit_pg.py -q -s"
  "tests/quick/test_outbound_concurrency_pg.py -q -s"
  "tests/quick/test_new_platforms_pg.py -q -s"
  "tests/quick/test_platform_multi_shop_pg.py -q -s"
)

# Smoke 测试集合
SMOKE_SUITES=(
  "tests/smoke/test_platform_events_smoke_pg.py -q -s"
)

# ------------------ 工具函数 ------------------

banner() {
  echo -e "\n\033[1;36m==== $* ====\033[0m\n"
}

parse_db_host_port() {
  python - "$DATABASE_URL" <<'PY'
import sys, urllib.parse as U
u = sys.argv[1].replace("+psycopg","")   # e.g. postgresql://…
p = U.urlparse(u)
print((p.hostname or "127.0.0.1"), (p.port or 5432))
PY
}

wait_for_db() {
  local host port
  read -r host port < <(parse_db_host_port)
  echo "⏳ Waiting for PostgreSQL at $host:$port ..."
  # 预热：给容器几秒启动时间，避免冷启动未监听导致的假失败
  sleep 3
  for i in {1..60}; do
    if command -v pg_isready >/dev/null 2>&1; then
      pg_isready -h "$host" -p "$port" >/dev/null 2>&1 && {
        echo "✅ PostgreSQL is ready."
        return 0
      }
    fi
    # 兜底：用 psql 探测
    if command -v psql >/dev/null 2>&1; then
      PGPASSWORD=${PGPASSWORD:-wms} psql "postgresql://wms:${PGPASSWORD}@$host:$port/wsca" -c 'select 1;' >/dev/null 2>&1 && {
        echo "✅ PostgreSQL is ready."
        return 0
      }
    fi
    sleep 2
  end=$((SECONDS+120))
  echo "❌ Timeout waiting for PostgreSQL ($host:$port)"
  return 1
}

migrate() {
  banner "Run Alembic migrations"
  export ALEMBIC_CONFIG=${ALEMBIC_CONFIG:-alembic.ini}
  alembic upgrade head
}

run_pytest_suites() {
  local -n arr=$1
  for spec in "${arr[@]}"; do
    echo "🧪 pytest ${spec}"
    pytest ${spec}
  done
}

# ------------------ 顶层命令 ------------------

cmd_env() {
  banner "Environment"
  echo "Python: $(python -V)"
  echo "PYTHONPATH: $PYTHONPATH"
  echo "DATABASE_URL: $DATABASE_URL"
  echo "WMS_SQLITE_GUARD: $WMS_SQLITE_GUARD"
  echo "----------"
  python - <<'PY'
import sys,platform; print("Executable:", sys.executable); print("Platform:", platform.platform())
PY
}

cmd_ci_prepare() {
  banner "Wait for DB + migrate"
  wait_for_db
  migrate
}

cmd_test_quick() {
  banner "Run QUICK test suites"
  run_pytest_suites QUICK_SUITES
}

cmd_test_smoke() {
  banner "Run SMOKE test suites"
  run_pytest_suites SMOKE_SUITES
}

cmd_ci_all() {
  cmd_env
  cmd_ci_prepare
  cmd_test_quick
  cmd_test_smoke
}

usage() {
  cat <<'USAGE'
Usage: ./run.sh <command>

Commands:
  ci:env            打印当前环境信息
  ci:pg:prepare     等待 PostgreSQL 可用并执行迁移
  ci:test:quick     运行快速测试集 (unit + small e2e)
  ci:test:smoke     运行端到端 smoke 测试
  ci:all            一键执行环境→迁移→quick→smoke

Examples:
  export DATABASE_URL='postgresql+psycopg://wms:wms@127.0.0.1:5433/wms'
  ./run.sh ci:env
  ./run.sh ci:pg:prepare
  ./run.sh ci:test:quick
  ./run.sh ci:test:smoke
  ./run.sh ci:all
USAGE
}

# ------------------ 入口 ------------------
case "${1:-}" in
  ci:env)          cmd_env ;;
  ci:pg:prepare)   cmd_ci_prepare ;;
  ci:test:quick)   cmd_test_quick ;;
  ci:test:smoke)   cmd_test_smoke ;;
  ci:all)          cmd_ci_all ;;
  *) usage; exit 1 ;;
esac
