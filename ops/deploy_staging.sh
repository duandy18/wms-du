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

# ✅ 默认只做 deploy，不启动 server（避免脚本把终端占住）
: "${WMS_RUN_SERVER:=0}"   # 1=启动 uvicorn；0=只部署不启动
: "${WMS_DAEMON:=0}"       # 1=后台启动（nohup）；0=前台启动（会阻塞终端）

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
python3 -V && pip -V
pip install -r requirements.txt
# 兜底：如 requirements 已含会跳过
pip install 'psycopg[binary]>=3.1' asyncpg >/dev/null 2>&1 || true

# --- 迁移 ---
echo "==[2/5] Alembic 迁移 =="
alembic upgrade head

# --- 最小域初始化（Phase 4E: lot-world） ---
echo "==[3/5] 初始化最小域 =="
python3 scripts/bootstrap_domain_min.py --store 主店A --items 777,778 || true

# --- 基线库存（Phase 4E：stocks_lot；lot_id=NULL 槽位） ---
echo "==[3.1/5] 写入基线库存（stocks_lot, lot_id=NULL） =="
psql "$PSQL_URL" -v ON_ERROR_STOP=1 -c "
  INSERT INTO warehouses(id,name) VALUES (1,'WH-1') ON CONFLICT (id) DO NOTHING;
  INSERT INTO items(id,sku,name,uom) VALUES (777,'SKU-777','ITEM-777','bag') ON CONFLICT (id) DO NOTHING;
  INSERT INTO items(id,sku,name,uom) VALUES (778,'SKU-778','ITEM-778','bag') ON CONFLICT (id) DO NOTHING;

  INSERT INTO stocks_lot(item_id, warehouse_id, lot_id, qty)
  VALUES (777, 1, NULL, 10)
  ON CONFLICT ON CONSTRAINT uq_stocks_lot_item_wh_lot DO UPDATE SET qty = EXCLUDED.qty;

  INSERT INTO stocks_lot(item_id, warehouse_id, lot_id, qty)
  VALUES (778, 1, NULL, 7)
  ON CONFLICT ON CONSTRAINT uq_stocks_lot_item_wh_lot DO UPDATE SET qty = EXCLUDED.qty;
"

# --- 启动（可选） ---
echo "==[4/5] 启动 API（可选） =="
if [[ "$WMS_RUN_SERVER" != "1" ]]; then
  echo ">> WMS_RUN_SERVER=$WMS_RUN_SERVER → 跳过启动（只部署不启动）"
  echo "   需要启动：WMS_RUN_SERVER=1 bash ops/deploy_staging.sh"
  echo "   后台启动：WMS_RUN_SERVER=1 WMS_DAEMON=1 bash ops/deploy_staging.sh"
else
  echo "   -> http://127.0.0.1:${WMS_PORT}/ping"
  if [[ "$WMS_DAEMON" == "1" ]]; then
    log="ops/.staging-uvicorn.log"
    echo ">> 后台启动（nohup），日志：$log"
    nohup uvicorn app.main:app --host "$WMS_HOST" --port "$WMS_PORT" --workers "$WMS_WORKERS" >"$log" 2>&1 &
    echo ">> uvicorn pid=$!"
  else
    echo ">> 前台启动（会阻塞终端；Ctrl+C 结束）"
    uvicorn app.main:app --host "$WMS_HOST" --port "$WMS_PORT" --workers "$WMS_WORKERS"
  fi
fi

# --- 健康检查（仅在不阻塞的情况下执行） ---
echo "==[5/5] 健康检查 =="
bash ops/healthcheck.sh || true
