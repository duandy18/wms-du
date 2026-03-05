#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
TOKEN="${TOKEN:?TOKEN env required}"

echo "== OK case (with province) =="
curl -sS -X POST "${BASE_URL}/platform-orders/ingest" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "platform": "PDD",
    "shop_id": "1",
    "ext_order_no": "EXT-DEMO-OK-003",
    "province": "广东省",
    "lines": [
      { "platform_sku_id": "SKU-INGEST-001", "qty": 1 }
    ]
  }' | jq .

echo
echo "== BLOCK case (missing province) =="
curl -sS -X POST "${BASE_URL}/platform-orders/ingest" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "platform": "PDD",
    "shop_id": "1",
    "ext_order_no": "EXT-DEMO-BLOCK-003",
    "lines": [
      { "platform_sku_id": "SKU-INGEST-001", "qty": 1 }
    ]
  }' | jq .
