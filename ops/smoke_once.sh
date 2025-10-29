#!/usr/bin/env bash
set -Eeuo pipefail
: "${PSQL_URL:?missing PSQL_URL}"
: "${WMS_PORT:=8000}"

ITEM=777
LOC=1

echo "== 基线可见量（调用现有 /stores/1/visible） =="
curl -fsS "http://127.0.0.1:${WMS_PORT}/stores/1/visible" | jq .

echo "== 入库+上架（不走接口，直接用 SQL 修改 stocks，并写一条 INBOUND 台账） =="
psql "$PSQL_URL" -v ON_ERROR_STOP=1 -c "
  -- 确保基线存在
  INSERT INTO warehouses(id,name) VALUES (1,'WH-1') ON CONFLICT (id) DO NOTHING;
  INSERT INTO locations(id,name,warehouse_id) VALUES (1,'L1',1) ON CONFLICT (id) DO NOTHING;
  INSERT INTO items(id,sku,name,unit) VALUES ($ITEM,'SKU-$ITEM','ITEM-$ITEM','bag') ON CONFLICT (id) DO NOTHING;
  INSERT INTO stocks(item_id,location_id,qty) VALUES ($ITEM,$LOC,0) ON CONFLICT (item_id,location_id) DO NOTHING;

  -- 增加 +5 并记录台账（after_qty=更新后的 qty）
  UPDATE stocks SET qty = COALESCE(qty,0) + 5 WHERE item_id=$ITEM AND location_id=$LOC;

  INSERT INTO stock_ledger (stock_id,item_id,delta,after_qty,occurred_at,reason,ref,ref_line)
  SELECT id, $ITEM, 5, qty, NOW(), 'INBOUND', 'SMOKE-INBOUND', 1
  FROM stocks WHERE item_id=$ITEM AND location_id=$LOC;
"

echo "== 结果核对（stocks / ledger） =="
psql "$PSQL_URL" -c "SELECT item_id,location_id,qty FROM stocks WHERE item_id IN (777,778) ORDER BY 1,2;"
psql "$PSQL_URL" -c "SELECT reason,ref,ref_line,item_id,delta,after_qty,occurred_at FROM stock_ledger WHERE item_id=$ITEM ORDER BY id DESC LIMIT 5;"

echo "== 可见量应随 physical 增长（reserved=0 时可见量=物理量） =="
curl -fsS "http://127.0.0.1:${WMS_PORT}/stores/1/visible" | jq .
