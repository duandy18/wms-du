#!/usr/bin/env bash
set -Eeuo pipefail

# 用法：source ops/env.example 后执行本脚本；或先 `export ...` 所有变量
: "${DATABASE_URL:?missing}"
: "${WMS_HOST:=0.0.0.0}"
: "${WMS_PORT:=8000}"
: "${WMS_WORKERS:=2}"

echo "==[1/6] 拉取主干并打稳定 Tag（可选）=="
git fetch --all -p
git checkout main
git pull --ff-only

echo "==[2/6] Python 依赖 =="
pip install -r requirements.txt

echo "==[3/6] 数据库迁移 =="
alembic upgrade head

echo "==[4/6] 最小域初始化（安全幂等）=="
python scripts/bootstrap_domain_min.py --store 主店A --items 777,778 || true
# 初始化基线库存（幂等更新）
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "UPDATE stocks SET qty=10 WHERE item_id=777 AND location_id=1;"
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "UPDATE stocks SET qty=7  WHERE item_id=778 AND location_id=1;"

echo "==[5/6] 启动后端（前台）=="
uvicorn app.main:app --host "$WMS_HOST" --port "$WMS_PORT" --workers "$WMS_WORKERS" &
WMS_PID=$!
sleep 1

echo "==[6/6] 健康检查 =="
curl -fsS "http://127.0.0.1:${WMS_PORT}/ping" | jq . >/dev/null
curl -fsS "http://127.0.0.1:${WMS_PORT}/stores/1/visible" | jq . >/dev/null
echo "Staging 启动成功 (PID=$WMS_PID)"
wait $WMS_PID
