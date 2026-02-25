#!/usr/bin/env bash
set -Eeuo pipefail
: "${PSQL_URL:?missing PSQL_URL}"
: "${WMS_PORT:=8000}"

ITEM=777
WH=1

echo "== 基线可见量（调用现有 /stores/1/visible） =="
curl -fsS "http://127.0.0.1:${WMS_PORT}/stores/1/visible" | jq .

echo "== 入库+上架（不走接口：直接改 stocks_lot + 写一条 INBOUND 台账） =="
psql "$PSQL_URL" -v ON_ERROR_STOP=1 -c "
  -- Phase 4E：location_id 退场；以 warehouse 为准
  INSERT INTO warehouses(id,name) VALUES ($WH,'WH-1') ON CONFLICT (id) DO NOTHING;
  INSERT INTO items(id,sku,name,uom) VALUES ($ITEM,'SKU-$ITEM','ITEM-$ITEM','bag') ON CONFLICT (id) DO NOTHING;

  -- 确保 lot_id=NULL 槽位存在（非批次商品/无 lot 槽位）
  INSERT INTO stocks_lot(item_id, warehouse_id, lot_id, qty)
  VALUES ($ITEM, $WH, NULL, 0)
  ON CONFLICT ON CONSTRAINT uq_stocks_lot_item_wh_lot DO NOTHING;

  -- 增加 +5
  UPDATE stocks_lot
     SET qty = COALESCE(qty,0) + 5
   WHERE item_id=$ITEM AND warehouse_id=$WH AND lot_id IS NULL;

  -- 写一条 INBOUND 台账（lot-world：batch_code 可为 NULL，lot_id 为 NULL）
  INSERT INTO stock_ledger (item_id, warehouse_id, lot_id, batch_code, delta, after_qty, occurred_at, reason, ref, ref_line)
  SELECT
    $ITEM,
    $WH,
    NULL,
    NULL,
    5,
    sl.qty,
    NOW(),
    'INBOUND',
    'SMOKE-INBOUND',
    1
  FROM stocks_lot sl
  WHERE sl.item_id=$ITEM AND sl.warehouse_id=$WH AND sl.lot_id IS NULL;
"

echo "== 结果核对（stocks_lot / ledger） =="
psql "$PSQL_URL" -c "SELECT item_id,warehouse_id,lot_id,qty FROM stocks_lot WHERE item_id IN (777,778) ORDER BY 1,2,3;"
psql "$PSQL_URL" -c "SELECT reason,ref,ref_line,item_id,warehouse_id,lot_id,batch_code,delta,after_qty,occurred_at FROM stock_ledger WHERE item_id=$ITEM ORDER BY id DESC LIMIT 5;"

echo "== 可见量应随 physical 增长（reserved=0 时可见量=物理量） =="
curl -fsS "http://127.0.0.1:${WMS_PORT}/stores/1/visible" | jq .
