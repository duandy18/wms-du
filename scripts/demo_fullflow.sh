#!/usr/bin/env bash
set -euo pipefail

BASE="http://127.0.0.1:8000"

echo "===== 0. 先种入库库存（scan: receive） ====="
curl -s -X POST "$BASE/scan" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "receive",
    "item_id": 1,
    "qty": 10,
    "warehouse_id": 1,
    "batch_code": "LIFE-BATCH-1",
    "production_date": "2025-01-01"
  }' | jq

echo
echo "===== 1. 生成 demo 订单（含基础库存种子逻辑） ====="
DEMO_JSON=$(
  curl -s -X POST "$BASE/dev/orders/demo?platform=PDD&shop_id=1"
)
echo "$DEMO_JSON"

EXT_NO=$(echo "$DEMO_JSON" | jq -r '.ext_order_no')
PLAT=$(echo "$DEMO_JSON" | jq -r '.platform')
SHOP=$(echo "$DEMO_JSON" | jq -r '.shop_id')
TRACE_ID=$(echo "$DEMO_JSON" | jq -r '.trace_id')

echo "EXT_NO=$EXT_NO PLAT=$PLAT SHOP=$SHOP TRACE_ID=$TRACE_ID"
ORDER_REF="ORD:${PLAT}:${SHOP}:${EXT_NO}"
echo "ORDER_REF=$ORDER_REF"

echo
echo "===== 2. 预占（reserve） ====="
curl -s -X POST "$BASE/orders/$PLAT/$SHOP/$EXT_NO/reserve" \
  -H "Content-Type: application/json" \
  -d '{
    "lines": [
      { "item_id": 1, "qty": 2 }
    ]
  }' | jq

echo
echo "===== 3. 拣货（pick）——扣库存 + 消耗软预占 ====="
curl -s -X POST "$BASE/orders/$PLAT/$SHOP/$EXT_NO/pick" \
  -H "Content-Type: application/json" \
  -d '{
    "warehouse_id": 1,
    "batch_code": "LIFE-BATCH-1",
    "lines": [
      { "item_id": 1, "qty": 2 }
    ]
  }' | jq

echo
echo "===== 4. 发货（ship-with-waybill）——写发货审计 + shipping_records ====="
curl -s -X POST "$BASE/orders/$PLAT/$SHOP/$EXT_NO/ship-with-waybill" \
  -H "Content-Type: application/json" \
  -d "{
    \"warehouse_id\": 1,
    \"carrier_code\": \"FAKE\",
    \"carrier_name\": \"Fake Express\",
    \"weight_kg\": 2.5,
    \"receiver_name\": \"测试用户\",
    \"receiver_phone\": \"13800000000\",
    \"province\": \"广东省\",
    \"city\": \"深圳市\",
    \"district\": \"南山区\",
    \"address_detail\": \"科技园某路 123 号\",
    \"meta\": {
      \"quote_snapshot\": {
        \"input\": {
          \"platform\": \"$PLAT\",
          \"shop_id\": \"$SHOP\",
          \"warehouse_id\": 1,
          \"carrier_code\": \"FAKE\",
          \"weight_kg\": 2.5,
          \"province\": \"广东省\",
          \"city\": \"深圳市\",
          \"district\": \"南山区\"
        },
        \"selected_quote\": {
          \"carrier_code\": \"FAKE\",
          \"carrier_name\": \"Fake Express\",
          \"total_amount\": 0,
          \"currency\": \"CNY\",
          \"reasons\": [\"DEMO_QUOTE_SNAPSHOT\"]
        }
      }
    }
  }" | jq
