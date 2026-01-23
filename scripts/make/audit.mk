# =================================
# audit.mk - 审计 / Phase 2&3 守门员
# =================================

.PHONY: audit-uom
audit-uom:
	@bash -c 'set -euo pipefail; \
	  echo "[audit-uom] scanning app/services for scattered qty_ordered * units_per_case ..."; \
	  hits="$$(rg -n "qty_ordered\\s*\\*\\s*units_per_case|units_per_case\\s*\\*\\s*qty_ordered" app/services -n || true)"; \
	  if [ -z "$$hits" ]; then \
	    echo "[audit-uom] OK (no hits)"; exit 0; \
	  fi; \
	  echo "$$hits"; \
	  if echo "$$hits" | rg -qv "^app/services/qty_base\\.py"; then \
	    echo "[audit-uom] FAIL: found scattered multiplication outside app/services/qty_base.py"; exit 1; \
	  fi; \
	  echo "[audit-uom] OK (only app/services/qty_base.py)";'

.PHONY: audit-consistency
audit-consistency:
	@bash -c 'set -euo pipefail; \
	  echo "[audit-consistency] forbid direct await write_ledger() usage outside infra modules ..."; \
	  hits="$$(rg -n "await\\s+write_ledger\\(" app/services \
	    --glob "!app/services/ledger_writer.py" \
	    --glob "!app/services/stock_service_adjust.py" \
	    --glob "!app/services/_deprecated/**" || true)"; \
	  if [ -z "$$hits" ]; then \
	    echo "[audit-consistency] OK (no hits)"; exit 0; \
	  fi; \
	  echo "$$hits"; \
	  echo ""; \
	  echo "[audit-consistency] FAIL: found direct await write_ledger() outside allowed infra modules"; \
	  echo "  allowed: app/services/ledger_writer.py, app/services/stock_service_adjust.py"; \
	  echo "  note: deprecated/* is ignored, but still recommended to delete/refactor"; \
	  exit 1;'

# =================================
# Phase 4 清理封口（PR-1）：禁止新增 legacy 引用
# =================================

.PHONY: audit-no-deprecated-import
audit-no-deprecated-import:
	@bash -c 'set -euo pipefail; \
	  echo "[audit-no-deprecated-import] forbid importing app/services/_deprecated from non-deprecated code ..."; \
	  hits="$$(rg -n "app\\.services\\._deprecated|services/_deprecated" app \
	    --glob "!app/services/_deprecated/**" || true)"; \
	  if [ -z "$$hits" ]; then \
	    echo "[audit-no-deprecated-import] OK (no hits)"; exit 0; \
	  fi; \
	  echo "$$hits"; \
	  echo "[audit-no-deprecated-import] FAIL: deprecated modules must not be imported by active code"; \
	  exit 1;'

.PHONY: audit-no-location-leak
audit-no-location-leak:
	@bash -c 'set -euo pipefail; \
	  echo "[audit-no-location-leak] forbid new location_id usage in active core code (allow explicit legacy/transition zones) ..."; \
	  hits="$$(rg -n "\\blocation_id\\b" app \
	    --glob "!app/api/routers/**" \
	    --glob "!app/schemas/**" \
	    --glob "!app/adapters/**" \
	    --glob "!app/ports.py" \
	    --glob "!app/domain/ports.py" \
	    --glob "!app/models/_inventory_legacy.py" \
	    --glob "!app/models/stock.py" \
	    --glob "!app/models/reservation_allocation.py" \
	    --glob "!app/models/inventory_movement.py" \
	    --glob "!app/models/pick_task_line.py" \
	    --glob "!app/services/_deprecated/**" \
	    --glob "!app/services/stock_helpers_impl.py" \
	    --glob "!app/services/inventory_adjust.py" \
	    --glob "!app/services/reconcile_service.py" \
	    --glob "!app/services/batch_service.py" \
	    --glob "!app/services/inventory_ops.py" \
	    --glob "!app/services/platform_adapter.py" \
	    --glob "!app/services/putaway_service.py" \
	    --glob "!app/services/pick_service.py" \
	    --glob "!app/services/fefo_allocator.py" \
	    --glob "!app/services/README.md" \
	    || true)"; \
	  if [ -z "$$hits" ]; then \
	    echo "[audit-no-location-leak] OK (no hits)"; exit 0; \
	  fi; \
	  echo "$$hits"; \
	  echo "[audit-no-location-leak] FAIL: location_id leaked into active core code; keep it inside legacy/transition zones only"; \
	  exit 1;'

# =================================
# Route C 封口：禁止主线回潮到 fallback/候选选仓
# =================================
.PHONY: audit-fulfillment-routec
audit-fulfillment-routec:
	@bash -c 'set -euo pipefail; \
	  echo "[audit-fulfillment-routec] forbid fallback routing semantics in fulfillment mainline ..."; \
	  hits="$$(rg -n "store_province_routes|route_mode|STRICT_TOP|auto_routed_fallback|WarehouseRouter\\(" \
	    app/services/order_ingest_service.py app/services/order_ingest_routing.py || true)"; \
	  if [ -z "$$hits" ]; then \
	    echo "[audit-fulfillment-routec] OK (no hits)"; exit 0; \
	  fi; \
	  echo "$$hits"; \
	  echo "[audit-fulfillment-routec] FAIL: fallback routing leaked into Route C mainline"; \
	  exit 1;'

# =================================
# Phase 5.1 封口：禁止任何隐性写 orders.warehouse_id
# - 白名单仅允许：manual-assign service（devconsole 写入已被禁止）
# =================================
.PHONY: audit-no-implicit-warehouse-id
audit-no-implicit-warehouse-id:
	@bash -c 'set -euo pipefail; \
	  echo "[audit-no-implicit-warehouse-id] forbid implicit writes to orders.warehouse_id ..."; \
	  hits="$$(rg -n "UPDATE orders\\s+SET\\s+warehouse_id|SET\\s+warehouse_id\\s*=" app -S || true)"; \
	  if [ -z "$$hits" ]; then \
	    echo "[audit-no-implicit-warehouse-id] OK (no hits)"; exit 0; \
	  fi; \
	  allow_re="app/services/order_fulfillment_manual_assign\\.py"; \
	  bad="$$(printf "%s\n" "$$hits" | rg -v "$$allow_re" || true)"; \
	  if [ -n "$$bad" ]; then \
	    echo "$$bad"; \
	    echo "[audit-no-implicit-warehouse-id] FAIL: only manual-assign service may write orders.warehouse_id"; \
	    exit 1; \
	  fi; \
	  echo "[audit-no-implicit-warehouse-id] OK (hits only in whitelist)"; \
	'

# =================================
# Phase 2 守门员：运价区间必须兜底覆盖（避免 no matching bracket 线上翻车）
# =================================
.PHONY: audit-pricing-brackets
audit-pricing-brackets: venv
	@bash -c 'set -euo pipefail; \
	  export PYTHONPATH=. ; \
	  export WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)"; \
	  export WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)"; \
	  echo "[audit-pricing-brackets] scanning pricing zones/brackets on TEST DB ($(DEV_TEST_DB_DSN)) ..."; \
	  "$(PY)" scripts/audit_pricing_brackets.py;'

.PHONY: audit-all
audit-all: audit-uom audit-consistency audit-no-deprecated-import audit-no-location-leak audit-fulfillment-routec audit-no-implicit-warehouse-id audit-pricing-brackets
	@echo "[audit-all] OK"

# =================================
# 制度化：seed baseline 后按 stocks 补齐 opening ledger
# =================================
.PHONY: seed-opening-ledger-test
seed-opening-ledger-test: venv
	@bash -c 'set -euo pipefail; \
	  export PYTHONPATH=. ; \
	  export WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)"; \
	  export WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)"; \
	  echo "[seed-opening-ledger-test] backfill opening ledger from stocks on TEST DB ($(DEV_TEST_DB_DSN)) ..."; \
	  "$(PY)" scripts/backfill_opening_ledger_from_stocks.py;'

# =================================
# 三账一致性自检（Phase 3 MVP）
# =================================
.PHONY: audit-three-books
audit-three-books: venv
	@bash -c 'set -euo pipefail; \
	  export PYTHONPATH=. ; \
	  export WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)"; \
	  export WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)"; \
	  args=""; \
	  if [ -n "$${REF:-}" ]; then args="$$args --ref $${REF}"; fi; \
	  if [ -n "$${TRACE_ID:-}" ]; then args="$$args --trace-id $${TRACE_ID}"; fi; \
	  if [ -n "$${LIMIT:-}" ]; then args="$$args --limit $${LIMIT}"; fi; \
	  if [ "$${IGNORE_OPENING:-0}" = "1" ] || [ "$${IGNORE_OPENING:-}" = "true" ]; then args="$$args --ignore-opening"; fi; \
	  echo "[audit-three-books] running snapshot + compare on TEST DB ($(DEV_TEST_DB_DSN)) $$args ..."; \
	  "$(PY)" scripts/audit_three_books.py $$args;'
