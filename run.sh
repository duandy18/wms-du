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
export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"
export PYTHONPATH="${PYTHONPATH:-.}"
export WMS_SQLITE_GUARD="${WMS_SQLITE_GUARD:-1}"
# 本地默认 5433；CI 通过 workflow 的 env 覆盖为 5433(容器5432→host5433) 或其它
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://wms:wms@127.0.0.1:5433/wms}"
export ALEMBIC_CONFIG="${ALEMBIC_CONFIG:-alembic.ini}"

# Quick 测试集合
QUICK_SUITES=(
  "tests/quick/test_platform_outbound_commit_pg.py -q -s"
  "tests/quick/test_outbound_concurrency_pg.py -q -s"
  "tests/quick/test_new_platforms_pg.py -q -s"
  "tests/quick/test_platform_multi_shop_pg.py -q -s"
)

# Smoke 测试集合
SMOKE_SUITES=(
  "tests/smoke/test_platform_events_bootstrap_pg.yml" # 只留一个入口文件即可，若你已有其他名称，请改成实际文件
)

# ------------------ 辅助函数 ------------------

banner() {
  echo -e "\n\033[1;36m==== $* ====\033[0m\n"
}

# 解析 PostgreSQL 连接串（纯 Bash；支持 postgresql:// 或 postgresql+psycopg://）
# 输出：<host> <port> <user> <pass> <db>
parse_db_parts() {
  local url="${DATABASE_URL#postgresql://}"
  url="${url#postgresql+psycopg://}"
  # 形如 user:pass@host:port/db?params 或 host:port/db
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
  fi
  db="${hostport#*/}"; db="${db%%\?*}"
  host="${hostport%%:*}"
  port="${hostport#*:}"
  [[ "$port" == "$hostport" ]] && port=5432
  echo "$host" "$port" "$user" "$pass" "$db"
}

wait_for_db() {
  local host port user pass db
  read -r host port user pass db < <(parse_db_parts)
  banner "Waiting for PostgreSQL at $host:$port"
  # 预热 3 秒，防止容器刚启动端口未开放
  sleep 3
  for i in {1..60}; do
    if command -v pg_isready >/dev/null 2>&1; then
      if pg_isready -h "$host" -p "$port" -U "$user" >/dev/null 2>&1; then
        echo "✅ Postgres is ready (pg_isready)."
        return 0
      fi
    fi
    if command -v psql >/dev/null 2>&1; then
      PGPASSWORD="${pass}" psql "postgresql://${user}:${pass}@${host}:${port}/${db}" -c 'select 1;' >/dev/null 2>&1 && {
        echo "✅ Postgres is ready (psql)."
        return 0
      }
    fi
    sleep 2
  done
  echo "❌ Timeout waiting for PostgreSQL at ${host}:${port}"
  return 1
}

migrate() {
  banner "Run Alembic migrations → ${ALEMBIC_CONFIG}"
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
  echo "PYTHONPATH: ${PYTHONPATH}"
  echo "DATABASE_URL: ${DATABASE_URL}"
  echo "WMS_SQLITE_GUARD: ${WMS_SQLITE_GUARD}"
  echo "-------------"
  python - <<'PY' || true
import sys, platform
print("Executable:", sys.executable)
print("Platform:", platform.platform())
PY
}

cmd_ci_prepare() {
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
  ci:all            一键执行 环境 → 迁移 → quick → smoke

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
