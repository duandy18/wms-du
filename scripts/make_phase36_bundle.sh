#!/usr/bin/env bash
set -euo pipefail

# 从脚本所在目录推到仓库根目录
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

LIST_FILE="$ROOT_DIR/phase36_files.txt"
TAR_FILE="$ROOT_DIR/phase36_bundle_$(date +%Y%m%d_%H%M%S).tar.gz"

# 这里是我们上一条消息里要看的文件清单
FILES=(
  # === models / db ===
  "app/models/store.py"
  "app/models/warehouse.py"
  "app/models/platform_shops.py"
  "app/models/order.py"
  "app/models/order_item.py"
  "app/models/reservation.py"
  "app/models/reservation_line.py"
  "app/models/outbound_commit.py"
  "app/models/stock.py"
  "app/models/stock_ledger.py"
  "app/models/__init__.py"
  "app/db/base.py"

  # === services ===
  "app/services/store_service.py"
  "app/services/order_service.py"
  "app/services/reservation_service.py"
  "app/services/reservation_consumer.py"
  "app/services/soft_reserve_service.py"
  "app/services/outbound_service.py"
  "app/services/platform_events.py"
  "app/services/ship_service.py"
  "app/services/channel_inventory_service.py"
  "app/services/stock_service.py"
  "app/services/stock_fallbacks.py"
  "app/services/ledger_writer.py"
  "app/services/audit_logger.py"
  "app/services/audit_writer.py"

  # === API routers & schemas ===
  "app/api/routers/orders.py"
  "app/api/routers/outbound.py"
  "app/api/routers/outbound_ship.py"
  "app/api/routers/reserve_soft.py"
  "app/api/routers/platform_shops.py"
  "app/api/routers/store.py"
  "app/api/routers/stores.py"
  "app/api/routers/inventory.py"
  "app/api/inventory.py"

  "app/schemas/order.py"
  "app/schemas/order_item.py"
  "app/schemas/outbound.py"
  "app/schemas/inventory.py"
  "app/schemas/reserve_soft.py"

  # === tests: 订单 / 店铺绑定 / 多店 ===
  "tests/api/test_orders_auto_ensure_store.py"
  "tests/api/test_orders_create_contract.py"
  "tests/api/test_orders_multi_platform_idempotent.py"
  "tests/services/test_store_binding_contract.py"
  "tests/services/test_store_service.py"
  "tests/services/test_order_service.py"
  "tests/services/test_order_outbound_flow_v3.py"
  "tests/quick/test_platform_multi_shop_pg.py"

  # === tests: 出库 & SoftReserve 链路 ===
  "tests/api/test_outbound_commit_contract.py"
  "tests/api/test_outbound_ship_commit_contract.py"
  "tests/api/test_outbound_ship_commit_http.py"
  "tests/services/test_outbound_service.py"
  "tests/services/test_outbound_service_adjust_path.py"
  "tests/services/soft_reserve/test_reservation_consumer_integration.py"
  "tests/services/soft_reserve/test_reserve_persist_idem.py"
  "tests/services/soft_reserve/test_pick_consume_idem.py"
  "tests/services/test_order_reserve_anti_oversell.py"
  "tests/quick/test_platform_outbound_commit_pg.py"
  "tests/quick/test_platform_events_pg.py"
  "tests/quick/test_platform_state_machine_pg.py"
  "tests/services/test_platform_events.py"
  "tests/services/test_platform_ship_soft_reserve.py"

  # === tests: 可售库存 / 视图 ===
  "tests/services/test_channel_inventory_service.py"
  "tests/services/test_channel_inventory_available.py"
  "tests/services/test_reservation_available_view.py"
  "tests/services/test_outbound_available_view.py"
)

echo "ROOT_DIR = $ROOT_DIR"
echo "Generating file list at $LIST_FILE"
: > "$LIST_FILE"

missing=0

for f in "${FILES[@]}"; do
  if [[ -f "$ROOT_DIR/$f" ]]; then
    echo "$f" >> "$LIST_FILE"
  else
    echo "WARN: missing $f" >&2
    missing=$((missing + 1))
  fi
done

if [[ $missing -gt 0 ]]; then
  echo "NOTE: there are $missing missing paths (see warnings above)."
fi

cd "$ROOT_DIR"
echo "Creating tarball $TAR_FILE ..."
tar czf "$TAR_FILE" -T "$LIST_FILE"

echo "Done."
echo "Packed files list: $LIST_FILE"
echo "Bundle to upload:  $TAR_FILE"
