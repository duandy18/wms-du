#!/usr/bin/env bash
set -euo pipefail

BASE="http://127.0.0.1:8000"

PLAT="PDD"
SHOP="1"
EXT="ORD-MULTI-$(date +%Y%m%d-%H%M%S)"
ORDER_REF="ORD:${PLAT}:${SHOP}:${EXT}"

WH=1
BATCH="LIFE-BATCH-1"

ITEM_A=1
QTY_A=2

ITEM_B=3003
QTY_B=1

now_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

TOKEN=$(curl -fsS -X POST "$BASE/users/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | jq -r .access_token)

echo "===== 0) Create Order (multi lines) ====="
echo "[order] ORDER_REF=$ORDER_REF"
curl -fsS -X POST "$BASE/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"platform\": \"$PLAT\",
    \"shop_id\": \"$SHOP\",
    \"ext_order_no\": \"$EXT\",
    \"occurred_at\": \"$now_utc\",
    \"buyer_name\": \"测试用户\",
    \"buyer_phone\": \"13800000000\",
    \"order_amount\": 0,
    \"pay_amount\": 0,
    \"lines\": [
      {\"item_id\": $ITEM_A, \"qty\": $QTY_A, \"title\": \"商品A\"},
      {\"item_id\": $ITEM_B, \"qty\": $QTY_B, \"title\": \"商品B\"}
    ]
  }" | jq .

echo
echo "===== 0.5) DEV: force set orders.warehouse_id=$WH (bypass store binding) ====="
psql "postgresql://wms:wms@127.0.0.1:5433/wms" -v ON_ERROR_STOP=1 -c \
  "UPDATE orders SET warehouse_id = $WH WHERE platform = '$PLAT' AND shop_id = '$SHOP' AND ext_order_no = '$EXT';"

echo
echo "===== 1) Seed stock for item A (scan receive) ====="
curl -fsS -X POST "$BASE/scan" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"mode\": \"receive\",
    \"item_id\": $ITEM_A,
    \"qty\": 50,
    \"warehouse_id\": $WH,
    \"batch_code\": \"$BATCH\",
    \"production_date\": \"2025-01-01\"
  }" | jq .

echo
echo "===== 1.1) Wait until next minute to avoid scan_ref collision ====="
start_min=$(date -u +%Y%m%d%H%M)
for i in $(seq 1 350); do
  now_min=$(date -u +%Y%m%d%H%M)
  if [[ "$now_min" != "$start_min" ]]; then
    echo "[ok] minute changed: $start_min -> $now_min"
    break
  fi
  sleep 0.2
done

echo
echo "===== 1.2) Seed stock for item B (scan receive) ====="
curl -fsS -X POST "$BASE/scan" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"mode\": \"receive\",
    \"item_id\": $ITEM_B,
    \"qty\": 50,
    \"warehouse_id\": $WH,
    \"batch_code\": \"$BATCH\",
    \"production_date\": \"2025-01-01\"
  }" | jq .

echo
echo "===== 2) Reserve (multi lines) ====="
curl -fsS -X POST "$BASE/orders/$PLAT/$SHOP/$EXT/reserve" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"lines\": [
      { \"item_id\": $ITEM_A, \"qty\": $QTY_A },
      { \"item_id\": $ITEM_B, \"qty\": $QTY_B }
    ]
  }" | jq .

echo
echo "===== 3) Pick (multi lines, same batch) ====="
curl -fsS -X POST "$BASE/orders/$PLAT/$SHOP/$EXT/pick" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"warehouse_id\": $WH,
    \"batch_code\": \"$BATCH\",
    \"lines\": [
      { \"item_id\": $ITEM_A, \"qty\": $QTY_A },
      { \"item_id\": $ITEM_B, \"qty\": $QTY_B }
    ]
  }" | jq .

echo
echo "===== 4) Ship with waybill ====="
curl -fsS -X POST "$BASE/orders/$PLAT/$SHOP/$EXT/ship-with-waybill" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"warehouse_id\": $WH,
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
          \"warehouse_id\": $WH,
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
  }" | jq .

echo
echo "===== 5) Verify detail summary lines (should be >=2) ====="
curl -fsS "$BASE/return-tasks/order-refs/$ORDER_REF/detail" \
  -H "Authorization: Bearer $TOKEN" \
| jq '.summary.lines'

echo
echo "===== DONE ====="
echo "ORDER_REF=$ORDER_REF"
