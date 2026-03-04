#!/usr/bin/env bash
set -euo pipefail

BASE="http://127.0.0.1:8000"

PLAT="PDD"
SHOP="1"
EXT="ORD-MULTI-$(date +%Y%m%d-%H%M%S)-$$"
ORDER_REF="ORD:${PLAT}:${SHOP}:${EXT}"

WH=1
# Batch-as-Lot：允许同一批次（lot_code）多次入库；幂等由 ref/ref_line 控制。
# 支持外部注入 BATCH 用于重复跑同批次验证：
#   BATCH=FIXED-BATCH-001 bash scripts/demo_fullflow_multi_order_lines.sh
BATCH="${BATCH:-LIFE-BATCH-$(date +%Y%m%d-%H%M%S)-$$}"

ITEM_A=1
QTY_A=2

ITEM_B=3003
QTY_B=1

now_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

TOKEN="$(
  curl -fsS -X POST "$BASE/users/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin123"}' | jq -r '.access_token // empty'
)"

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
  echo "[demo_fullflow_multi] ERROR: login failed: access_token empty/null" >&2
  exit 1
fi

echo "===== 0) Create Order (multi lines) ====="
echo "[order] ORDER_REF=$ORDER_REF"
ORDER_JSON="$(
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
    }"
)"
echo "$ORDER_JSON" | jq .

echo
echo "===== 0.5) DEV: set order_fulfillment planned/actual=$WH (bypass store binding) ====="
# 说明：
# - 你们当前约束明确禁止 fulfillment_status 取 READY_TO_FULFILL/SHIP_COMMITTED/SHIPPED（ck_order_fulfillment_status_no_ship_stage）
# - 因此脚本不再写 fulfillment_status，只设置 planned/actual warehouse 并清空 blocked_reasons
psql "postgresql://wms:wms@127.0.0.1:5433/wms" -v ON_ERROR_STOP=1 -c "
WITH o AS (
  SELECT id
    FROM orders
   WHERE platform = '${PLAT}'
     AND shop_id = '${SHOP}'
     AND ext_order_no = '${EXT}'
   ORDER BY id DESC
   LIMIT 1
)
INSERT INTO order_fulfillment (
  order_id,
  planned_warehouse_id,
  actual_warehouse_id,
  blocked_reasons
)
SELECT
  o.id,
  ${WH},
  ${WH},
  NULL
FROM o
ON CONFLICT (order_id) DO UPDATE
   SET planned_warehouse_id = EXCLUDED.planned_warehouse_id,
       actual_warehouse_id  = EXCLUDED.actual_warehouse_id,
       blocked_reasons      = NULL;
"

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
echo "===== 1.1) Wait until next minute to avoid scan_ref collision (optional) ====="
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
echo "===== 2) Pick (multi lines) ====="
# reserve 概念已退役：脚本不再调用 /reserve
# 合同收口：pick 不传 batch_code
PICK_OUT="$(mktemp)"
PICK_HTTP="$(curl -sS -o "$PICK_OUT" -w "%{http_code}" -X POST "$BASE/orders/$PLAT/$SHOP/$EXT/pick" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"warehouse_id\": $WH,
    \"lines\": [
      { \"item_id\": $ITEM_A, \"qty\": $QTY_A },
      { \"item_id\": $ITEM_B, \"qty\": $QTY_B }
    ]
  }" || true)"
cat "$PICK_OUT" | jq .
rm -f "$PICK_OUT"
echo "[http_status]=$PICK_HTTP" >&2
if [[ "$PICK_HTTP" -lt 200 || "$PICK_HTTP" -ge 300 ]]; then
  echo "[demo_fullflow_multi] ERROR: pick failed (http=$PICK_HTTP). abort." >&2
  exit 1
fi

echo
echo "===== 3) Ship with waybill ====="
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
echo "===== 4) Verify detail summary lines (should be >=2) ====="
curl -fsS "$BASE/return-tasks/order-refs/$ORDER_REF/detail" \
  -H "Authorization: Bearer $TOKEN" \
| jq '.summary.lines'

echo
echo "===== DONE ====="
echo "ORDER_REF=$ORDER_REF"
