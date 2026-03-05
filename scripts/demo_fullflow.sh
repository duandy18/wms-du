#!/usr/bin/env bash
set -euo pipefail

BASE="http://127.0.0.1:8000"
DB_DSN="postgresql://wms:wms@127.0.0.1:5433/wms"

# Batch-as-Lot：允许同一批次（lot_code）多次入库；幂等由 (reason, ref, ref_line, item, wh, lot) 控制。
# 支持外部注入 BATCH 以验证“同批次多次入库复用同一 lot”：
#   BATCH=FIXED-BATCH-001 bash scripts/demo_fullflow.sh
BATCH="${BATCH:-LIFE-BATCH-$(date +%Y%m%d-%H%M%S)-$$}"

post_json() {
  local url="$1"
  local data="$2"

  local out http body
  out="$(mktemp)"
  http="$(curl -sS -o "$out" -w "%{http_code}" -X POST "$url" -H "Content-Type: application/json" -d "$data" || true)"
  body="$(cat "$out")"
  rm -f "$out"

  echo "[http_status]=$http" >&2
  if [[ "$http" -lt 200 || "$http" -ge 300 ]]; then
    # 非 2xx 时也把 body 打出来，便于定位
    echo "$body"
    echo >&2 "[demo_fullflow] ERROR: request failed: POST $url (http=$http)"
    exit 1
  fi

  echo "$body"
}

echo "===== 0. 先种入库库存（scan: receive） ====="
SCAN_BODY="$(post_json "$BASE/scan" "{
  \"mode\": \"receive\",
  \"item_id\": 1,
  \"qty\": 10,
  \"warehouse_id\": 1,
  \"batch_code\": \"$BATCH\",
  \"production_date\": \"2025-01-01\"
}")"
echo "$SCAN_BODY" | jq
if echo "$SCAN_BODY" | jq -e 'has("ok") and (.ok|not)' >/dev/null; then
  echo >&2 "[demo_fullflow] ERROR: scan receive returned ok=false"
  exit 1
fi

echo
echo "===== 1. 生成 demo 订单（含基础库存种子逻辑） ====="
DEMO_BODY="$(post_json "$BASE/dev/orders/demo?platform=PDD&shop_id=1" "")"
echo "$DEMO_BODY" | jq 2>/dev/null || echo "$DEMO_BODY"

EXT_NO="$(echo "$DEMO_BODY" | jq -r '.ext_order_no // empty')"
PLAT="$(echo "$DEMO_BODY" | jq -r '.platform // empty')"
SHOP="$(echo "$DEMO_BODY" | jq -r '.shop_id // empty')"
TRACE_ID="$(echo "$DEMO_BODY" | jq -r '.trace_id // empty')"

if [ -z "$EXT_NO" ] || [ "$EXT_NO" = "null" ]; then
  echo >&2 "[demo_fullflow] ERROR: create demo order failed: ext_order_no is empty/null"
  exit 1
fi
if [ -z "$PLAT" ] || [ "$PLAT" = "null" ]; then
  echo >&2 "[demo_fullflow] ERROR: create demo order failed: platform is empty/null"
  exit 1
fi
if [ -z "$SHOP" ] || [ "$SHOP" = "null" ]; then
  echo >&2 "[demo_fullflow] ERROR: create demo order failed: shop_id is empty/null"
  exit 1
fi
if [ -z "$TRACE_ID" ] || [ "$TRACE_ID" = "null" ]; then
  echo >&2 "[demo_fullflow] ERROR: create demo order failed: trace_id is empty/null"
  exit 1
fi

echo "EXT_NO=$EXT_NO PLAT=$PLAT SHOP=$SHOP TRACE_ID=$TRACE_ID"
ORDER_REF="ORD:${PLAT}:${SHOP}:${EXT_NO}"
echo "ORDER_REF=$ORDER_REF"

echo
echo "===== 1.5 DEV: 绑定执行仓（order_fulfillment.actual_warehouse_id=1） ====="
# 注意：
# - reserve 概念已退役：不再调用 /reserve
# - 进入执行链路必须绑定 actual_warehouse_id（authority），否则 pick 会拒绝
# - 不写 fulfillment_status（避免 ck_order_fulfillment_status_no_ship_stage）
psql "$DB_DSN" -v ON_ERROR_STOP=1 -c "
WITH o AS (
  SELECT id
    FROM orders
   WHERE platform = '${PLAT}'
     AND shop_id = '${SHOP}'
     AND ext_order_no = '${EXT_NO}'
   ORDER BY id DESC
   LIMIT 1
)
INSERT INTO order_fulfillment (order_id, planned_warehouse_id, actual_warehouse_id, blocked_reasons)
SELECT o.id, 1, 1, NULL
FROM o
ON CONFLICT (order_id) DO UPDATE
   SET planned_warehouse_id = COALESCE(order_fulfillment.planned_warehouse_id, EXCLUDED.planned_warehouse_id),
       actual_warehouse_id  = EXCLUDED.actual_warehouse_id,
       blocked_reasons      = NULL,
       updated_at           = now();
"

echo
echo "===== 2. 拣货（pick）——扣库存 ====="
# 合同收口：pick 不传 batch_code（由后端按 lot-world 规则处理）
PICK_BODY="$(post_json "$BASE/orders/$PLAT/$SHOP/$EXT_NO/pick" '{
  "warehouse_id": 1,
  "lines": [
    { "item_id": 1, "qty": 2, "batch_code": "${BATCH}" }
  ]
}')"
echo "$PICK_BODY" | jq 2>/dev/null || echo "$PICK_BODY"

echo
echo "===== 3. 发货（ship-with-waybill）——写发货审计 + shipping_records ====="
SHIP_BODY="$(post_json "$BASE/orders/$PLAT/$SHOP/$EXT_NO/ship-with-waybill" "{
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
}")"
echo "$SHIP_BODY" | jq 2>/dev/null || echo "$SHIP_BODY"
