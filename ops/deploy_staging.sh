#!/usr/bin/env bash
set -Eeuo pipefail

echo "== WMS-DU :: deploy_staging =="

# --- 环境与变量 ---
# 可先: source ops/env.example
# 优先使用 PSQL_URL；若未设置则从 DATABASE_URL 推导
: "${DATABASE_URL:?missing DATABASE_URL (e.g. postgresql+psycopg://wms:wms@127.0.0.1:5433/wms)}"
PSQL_URL_DEFAULT="${DATABASE_URL/+psycopg/}"
: "${PSQL_URL:=$PSQL_URL_DEFAULT}"

: "${TZ:=Asia/Shanghai}"
: "${PYTHONPATH:=.}"
: "${WMS_HOST:=0.0.0.0}"
: "${WMS_PORT:=8000}"
: "${WMS_WORKERS:=2}"

export TZ PYTHONPATH

# --- Git 步骤（可跳过） ---
if [[ "${SKIP_GIT_PULL:-0}" == "1" ]]; then
  echo ">> SKIP_GIT_PULL=1 → 跳过 git fetch/checkout/pull"
else
  if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "[ABORT] 工作区存在未提交变更。请先提交或 stash；或用 SKIP_GIT_PULL=1 跳过 git 步骤。"
    exit 2
  fi
  git fetch --all -p
  git checkout main
  git pull --ff-only
fi

# --- 依赖 ---
echo "==[1/5] 安装依赖 =="
python -V && pip -V
pip install -r requirements.txt
# 兜底：如 requirements 已含会跳过
pip install 'psycopg[binary]>=3.1' asyncpg >/dev/null 2>&1 || true

# --- 迁移 ---
echo "==[2/5] Alembic 迁移 =="
alembic upgrade head

# --- 最小域初始化 + 基线库存 ---
echo "==[3/5] 初始化最小域 =="
python scripts/bootstrap_domain_min.py --store 主店A --items 777,778 || true
psql "$PSQL_URL" -v ON_ERROR_STOP=1 -c "UPDATE stocks SET qty=10 WHERE item_id=777 AND location_id=1;"
psql "$PSQL_URL" -v ON_ERROR_STOP=1 -c "UPDATE stocks SET qty=7  WHERE item_id=778 AND location_id=1;"

# --- 启动（前台便于观察日志；需要后台可改为 systemd） ---
echo "==[4/5] 启动 API（前台） =="
echo "   -> http://127.0.0.1:${WMS_PORT}/ping"
uvicorn app.main:app --host "$WMS_HOST" --port "$WMS_PORT" --workers "$WMS_WORKERS"
# 注意：前台阻塞；若你想后台运行，可改为在 systemd 中管理。

# --- 健康检查（仅当前台退出后才会执行，一般不会到达）---
echo "==[5/5] 健康检查 =="
bash ops/healthcheck.sh || true
