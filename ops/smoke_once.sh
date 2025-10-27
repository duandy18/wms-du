#!/usr/bin/env bash
set -Eeuo pipefail
: "${DATABASE_URL:?missing}"
: "${WMS_PORT:=8000}"

echo "== 入库 777: +5 =="
curl -fsS -X POST "http://127.0.0.1:${WMS_PORT}/inbound/receive" \
  -H 'Content-Type: application/json' \
  -d '{"item_id":777,"accepted_qty":5}' | jq .

echo "== 上架到 loc=1: +5 =="
curl -fsS -X POST "http://127.0.0.1:${WMS_PORT}/inbound/putaway" \
  -H 'Content-Type: application/json' \
  -d '{"item_id":777,"location_id":1,"qty":5}' | jq .

echo "== Stocks / Ledger =="
psql "$DATABASE_URL" -c "SELECT item_id,location_id,qty FROM stocks WHERE item_id IN (777,778) ORDER BY 1,2;"
psql "$DATABASE_URL" -c "SELECT reason,ref,ref_line,item_id,delta,after_qty,occurred_at FROM stock_ledger WHERE item_id=777 ORDER BY id DESC LIMIT 10;"

echo "== 快照触发 =="
curl -fsS -X POST "http://127.0.0.1:${WMS_PORT}/snapshot/run" | jq .
curl -fsS      "http://127.0.0.1:${WMS_PORT}/snapshot/inventory" | jq .
