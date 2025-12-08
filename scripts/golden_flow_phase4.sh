#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8000}"

if [[ -z "${WMS_TOKEN:-}" ]]; then
  echo "[ERROR] WMS_TOKEN 未设置，请先登录获取 token，并 export WMS_TOKEN=..."
  exit 1
fi

H="Authorization: Bearer $WMS_TOKEN"

echo "[1] 生成订单号 ..."
ORDER_NO="AUTO-$(date +%Y%m%d-%H%M%S)-ROUTE"
echo "ORDER_NO=$ORDER_NO"

echo "[2] /orders 下单 ..."
RESP=$(
  curl -s -X POST "$BASE/orders" \
    -H "$H" -H "Content-Type: application/json" \
    -d "{
      \"platform\": \"PDD\",
      \"shop_id\": \"1\",
      \"ext_order_no\": \"$ORDER_NO\",
      \"buyer_name\": \"黄金链路买家\",
      \"buyer_phone\": \"13800000000\",
      \"order_amount\": 50.0,
      \"pay_amount\": 50.0,
      \"lines\": [
        {
          \"item_id\": 1,
          \"title\": \"黄金链路测试商品\",
          \"qty\": 5,
          \"price\": 10.0,
          \"amount\": 50.0
        }
      ]
    }"
)

echo "$RESP" | jq
STATUS=$(echo "$RESP" | jq -r '.status')
ORDER_REF=$(echo "$RESP" | jq -r '.ref')
ORDER_ID=$(echo "$RESP" | jq -r '.id')
echo "STATUS=$STATUS"
echo "ORDER_REF=$ORDER_REF"
echo "ORDER_ID=$ORDER_ID"

echo "[3] 通过 DevConsole 拿 trace_id ..."
TRACE_ID=$(
  curl -s "$BASE/dev/orders/PDD/1/$ORDER_NO" \
    -H "$H" | jq -r '.trace_id'
)
echo "TRACE_ID=$TRACE_ID"

echo "[4] 初始 trace 关键事件（应有 ORDER_CREATED / WAREHOUSE_ROUTED）..."
curl -s "$BASE/debug/trace/$TRACE_ID" -H "$H" | jq '.events[0,1]'

echo "[5] 预占：/orders/PDD/1/$ORDER_NO/reserve ..."
curl -s -X POST "$BASE/orders/PDD/1/$ORDER_NO/reserve" \
  -H "$H" -H "Content-Type: application/json" \
  -d '{
    "lines": [
      { "item_id": 1, "qty": 5 }
    ]
  }' | jq

echo "[5.1] 预占后的 trace 关键事件（ORDER_RESERVED / RESERVE_APPLIED / reservation_open）..."
curl -s "$BASE/debug/trace/$TRACE_ID" -H "$H" | jq '.events[-4:]'

echo "[6] 拣货：/orders/PDD/1/$ORDER_NO/pick ..."
curl -s -X POST "$BASE/orders/PDD/1/$ORDER_NO/pick" \
  -H "$H" -H "Content-Type: application/json" \
  -d '{
    "warehouse_id": 1,
    "batch_code": "NEAR",
    "lines": [
      { "item_id": 1, "qty": 5 }
    ]
  }' | jq

echo "[6.1] 拣货 + 预占消耗后的 trace 关键事件 ..."
curl -s "$BASE/debug/trace/$TRACE_ID" -H "$H" | jq '.events[-5:]'

echo "[7] 发货：/orders/PDD/1/$ORDER_NO/ship ..."
curl -s -X POST "$BASE/orders/PDD/1/$ORDER_NO/ship" \
  -H "$H" -H "Content-Type: application/json" \
  -d "{
    \"warehouse_id\": 1,
    \"lines\": [
      { \"item_id\": 1, \"qty\": 5 }
    ]
  }" | jq

echo "[7.1] 查看订单最终状态（应为 SHIPPED）..."
curl -s "$BASE/dev/orders/PDD/1/$ORDER_NO" -H "$H" | jq '.order'

echo "[7.2] 最终 trace 关键事件（应包含 SHIP_COMMIT）..."
curl -s "$BASE/debug/trace/$TRACE_ID" -H "$H" | jq '.events'

echo "[DONE] Golden Flow 完整跑通。"
