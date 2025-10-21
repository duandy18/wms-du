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
# 本地默认 5433；CI 会覆写为 5432
export DATABASE_URL=${DATABASE_URL:-postgresql+psycopg://wms:wms@127.0.0.1:5433/wms}

# Quick 测试集合（可按需增删）
QUICK_SUITES=(
  "tests/quick/test_platform_outbound_commit_pg.py -q -s"
  "tests/quick/test_outbound_concurrency_pg.py -q -s"
  "tests/quick/test_new_platforms_pg.py -q -s"
  "tests/quick/test_platform_multi_shop_pg.py -q -s"
)

# Smoke 测试集合（E2E）
SMOKE_SUITES=(
  "tests/smoke/test_platform_events_smoke_pg.py -q -s"
)

# ------------------ 辅助函数 ------------------

banner() {
  echo -e "\n\033[1;36m==== $* ====\033[0m\n"
}

# 纯 Bash/Sed 解析 DATABASE_URL（避免 python/sitecustomize 干扰）
parse_db_host_port() {
  # postgresql+psycopg:// => postgresql://
  local url="${DATABASE_URL//+psycopg/}"
  # host
  local host
  host="$(printf '%s\n' "$url" | sed -E 's#.*://([^/@:]+)(:([0-9]+))?.*#\1#')"
  # port（默认 5432）
  local port
  port="$(printf '%s\n' "$url" | sed -nE 's#.*://[^/@:]+:([0-9]+).*#\1#p')"
  [[ -z "$host" || "$host" == "$url" ]] && host="127.0.0.1"
  [[ -z "$port" ]] && port=5432
  echo "$host $port"
}

wait_for_db() {
  local host port
  read -r host port < <(parse_db_host_port)
  echo "⏳ Waiting for PostgreSQL at $host:$port ..."

  # psql 可识别的 URL（去掉 +psycopg）
  local psql_url="${DATABASE_URL//+psycopg/}"

  for i in {1..60}; do
    # 优先 pg_isready
    if command -v pg_isready >/dev/null 2>&1; then
      if pg_isready -h "$host" -p "$port" >/dev/null 2>&1; then
        echo "✅ PostgreSQL is ready."
        return 0
      fi
    fi
    # 兜底：用 psql 冒烟
    if command -v psql >/dev/null 2>&1; then
      PGPASSWORD="${PGPASSWORD:-wms}" psql "$psql_url" -c 'select 1' >/dev/null 2>&1 && {
        echo "✅ PostgreSQL is ready."
        return 0
      }
    fi
    sleep 1
  done
  echo "❌ Timeout waiting for PostgreSQL on $host:$port"
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

# ------------------ 命令实现 ------------------

cmd_env() {
  banner "Environment"
  echo "Python:      $(python -V 2>/dev/null || true)"
  echo "PYTHONPATH:  $PYTHONPATH"
  echo "DATABASE_URL:$DATABASE_URL"
  echo "WMS_SQLITE_GUARD: $WMS_SQLITE_GUARD"
  echo "------------------------------"
  python - <<'PY' || true
try:
    import sys, platform
    print('Platform:', platform.platform())
    print('Executable:', sys.executable)
except Exception as e:
    print('Python inspect skipped:', e)
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

# ------------------ 命令分发 ------------------

case "${1:-}" in
  ci:env)          cmd_env ;;
  ci:pg:prepare)   cmd_ci_prepare ;;
  ci:test:quick)   cmd_test_quick ;;
  ci:test:smoke)   cmd_test_smoke ;;
  ci:all)          cmd_ci_all ;;
  *) usage; exit 1 ;;
esac
