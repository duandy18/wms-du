#!/usr/bin/env bash
set -euo pipefail

# 通用 helper 生成一个带 skip 的 stub
gen_legacy_stub() {
  local path="$1"
  local reason="$2"

  cat > "$path" << EOF
"""
Legacy API test: ${reason}

本文件对应的是接口早期设计的合同（多为 location_id / v1 StockService /
自动从 sku 建 order_items.item_id / 旧 scan 网关等），
当前实现已经升级为 v2 模型（warehouse+batch+SoftReserve），
并由新的 tests 覆盖行为。

此处仅保留为历史文档，不再参与当前测试基线。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=${reason@Q}
)
EOF
}

# 1) 订单相关老合同
gen_legacy_stub tests/api/test_orders_auto_ensure_store.py \
  "legacy /orders auto-ensure-store contract based on sku-only lines and nullable order_items.item_id"

gen_legacy_stub tests/api/test_orders_create_contract.py \
  "legacy /orders create contract that assumes order_items.item_id can be NULL or item rows auto-created"

gen_legacy_stub tests/api/test_orders_multi_platform_idempotent.py \
  "legacy OrderService.ingest HTTP-level contract using sku-only items; v2 requires explicit item_id and preseeded items"

# 2) old outbound/scanned outbound API 合同
gen_legacy_stub tests/api/test_outbound_commit_contract.py \
  "legacy outbound commit API test relying on preseeded SKU-001 and v1 scan/outbound flow"

gen_legacy_stub tests/api/test_outbound_reserve_pick_http.py \
  "legacy outbound reserve+pick HTTP E2E using batches.location_id and v1 reserve/pick contracts"

# 3) scan gateway old contracts
gen_legacy_stub tests/api/test_scan_gateway_count_commit.py \
  "legacy /scan/count/commit API contract using SKU-001 seed and v1 COUNT semantics"

gen_legacy_stub tests/api/test_scan_gateway_other_modes_probe.py \
  "legacy /scan probe contracts expecting minimal payload (node+barcode+qty) to be accepted; v2 requires structured item_id/location/batch_code"

gen_legacy_stub tests/api/test_scan_gateway_pick_commit.py \
  "legacy /scan pick commit API contract using SKU-001 and v1 scan schema"

gen_legacy_stub tests/api/test_scan_gateway_pick_commit_trace.py \
  "legacy /scan pick commit trace contract tied to v1 scan event structure"

gen_legacy_stub tests/api/test_scan_gateway_pick_probe.py \
  "legacy /scan pick probe event_log contract relying on v1 scan schema"

gen_legacy_stub tests/api/test_scan_gateway_putaway_commit.py \
  "legacy /scan putaway commit API contract; putaway flow is currently disabled and will be redesigned on v2 stock model"

gen_legacy_stub tests/api/test_scan_gateway_receive.py \
  "legacy /scan receive commit API contract using v1 receive schema"

gen_legacy_stub tests/api/test_scan_gateway_receive_commit.py \
  "legacy /scan receive commit + ledger contract using v1 receive schema"

# 4) stock ledger / batch query old contracts
gen_legacy_stub tests/api/test_stock_ledger.py \
  "legacy stock ledger HTTP query contract using stock_service fixture and location-based adjust()"

gen_legacy_stub tests/api/test_stock_ledger_export.py \
  "legacy stock ledger export CSV contract based on v1 StockService.adjust(location_id)"

gen_legacy_stub tests/api/test_stock_batch_query.py \
  "legacy stock batch query API test calling StockService.adjust(location_id); superseded by v2 stock/batch tests"

echo "Done. Legacy API tests have been converted to skipped stubs."
