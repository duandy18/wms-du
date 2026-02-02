# =================================
# test.mk - pytest 入口集合
# =================================

# ---------------------------------
# 统一护栏：测试库先升级到 head（避免新增表导致 UndefinedTable）
# ---------------------------------
.PHONY: upgrade-dev-test-db
upgrade-dev-test-db: venv
	@bash -c 'set -euo pipefail; \
	  dsn="$(DEV_TEST_DB_DSN)"; \
	  echo ">>> Alembic upgrade head on DEV_TEST_DB_DSN ($${dsn})"; \
	  if echo "$${dsn}" | grep -q "wms_test"; then \
	    echo "  MODE = TEST (wms_test) ✅"; \
	  else \
	    echo "  MODE = DEV / OTHER ⚠️  (CHECK!)"; \
	  fi; \
	  WMS_DATABASE_URL="$${dsn}" WMS_TEST_DATABASE_URL="$${dsn}" $(ALEMB) upgrade head'

.PHONY: test-core
test-core: venv audit-all upgrade-dev-test-db
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" $(PYTEST) -q -m grp_core -s

.PHONY: test-flow
test-flow: venv audit-all upgrade-dev-test-db
	@echo "[pytest] Flow tests (explicit file set)"
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" \
	$(PYTEST) -q -s \
	  tests/services/test_order_outbound_flow_v3.py \
	  tests/services/test_outbound_ledger_consistency.py \
	  tests/services/test_outbound_idempotency.py \
	  tests/services/test_trace_full_chain_order_reserve_outbound.py

.PHONY: test-snapshot
test-snapshot: venv audit-all upgrade-dev-test-db
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" $(PYTEST) -q -m grp_snapshot -s

# ---------------------------------
# 通用 pytest 入口（支持 TESTS=...）
# ---------------------------------
.PHONY: test
test: venv audit-all upgrade-dev-test-db
	@bash -c 'set -euo pipefail; \
	  export PYTHONPATH=. ; \
	  export WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)"; \
	  export WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)"; \
	  echo ""; \
	  echo "=================================================="; \
	  echo "[pytest] USING DATABASE:"; \
	  echo "  WMS_DATABASE_URL      = $${WMS_DATABASE_URL}"; \
	  echo "  WMS_TEST_DATABASE_URL = $${WMS_TEST_DATABASE_URL}"; \
	  if echo "$${WMS_DATABASE_URL}" | grep -q "wms_test"; then \
	    echo "  MODE = TEST (wms_test) ✅"; \
	  else \
	    echo "  MODE = DEV / OTHER ⚠️  (CHECK!)"; \
	  fi; \
	  echo "=================================================="; \
	  echo ""; \
	  if [ -n "$${TESTS:-}" ]; then \
	    echo ">>> TESTS=$${TESTS}"; \
	    "$(PYTEST)" -q -s $${TESTS}; \
	  else \
	    "$(PYTEST)" -q; \
	  fi'
	@$(MAKE) seed-opening-ledger-test
	@$(MAKE) audit-three-books

# ---------------------------------
# RBAC 专用测试入口
# ---------------------------------
.PHONY: test-rbac
test-rbac: venv audit-all upgrade-dev-test-db
	@echo "[pytest] RBAC tests – tests/api/test_user_api.py"
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" \
	$(PYTEST) -q -s tests/api/test_user_api.py

# ---------------------------------
# Internal Outbound 单元测试入口
# ---------------------------------
.PHONY: test-internal-outbound
test-internal-outbound: venv audit-all upgrade-dev-test-db
	@echo "[pytest] Internal Outbound Golden Flow E2E"
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" \
	$(PYTEST) -q -s tests/services/test_internal_outbound_service.py

# =================================
# Phase 5 CI Gate：Service Assignment（Route C 简化世界观）
# - 只写 service_warehouse_id
# - 不自动写 warehouse_id
# - ingest 阶段不 reserve
# =================================
.PHONY: test-phase5-service-assignment
test-phase5-service-assignment: venv audit-all upgrade-dev-test-db
	@echo "[pytest] Phase 5 service-assignment tests (Route C simplified worldview)"
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" \
	$(PYTEST) -q tests/phase5_service_assignment

# =================================
# ✅ Pick 蓝皮书：最小主线（scan facts + commit judgment + insufficient_stock + db evidence）
# =================================
.PHONY: test-pick-blueprint
test-pick-blueprint: venv audit-all upgrade-dev-test-db
	@echo "[pytest] Pick Blueprint (scan facts + commit judgment + insufficient_stock + db evidence)"
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" \
	$(PYTEST) -q -s \
	  tests/services/pick/test_pick_blueprint_contract.py \
	  tests/services/pick/test_pick_blueprint_commit_idempotency_contract.py \
	  tests/services/pick/test_pick_blueprint_insufficient_stock_contract.py \
	  tests/services/pick/test_pick_blueprint_db_evidence_contract.py

# =================================
# ✅ 全量回归（排除 legacy soft_reserve / phase2p9）
# =================================
.PHONY: test-no-legacy
test-no-legacy: venv audit-all upgrade-dev-test-db
	@echo "[pytest] Running full test suite excluding legacy soft_reserve (marker: legacy_soft_reserve)"
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" \
	$(PYTEST) -q -m "not legacy_soft_reserve"

# =================================
# 全量回归
# =================================
.PHONY: test-all
test-all: venv audit-all upgrade-dev-test-db
	@echo "[pytest] Running full test suite on DEV_TEST_DB_DSN ($(DEV_TEST_DB_DSN))"
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" $(PYTEST) -q

# =================================
# 核心服务 CRUD/UoW
# =================================
.PHONY: test-svc-core
test-svc-core: venv audit-all upgrade-dev-test-db
	@echo "[pytest] Core Service CRUD/UoW"
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" $(PYTEST) -q \
		tests/services/test_store_service.py \
		tests/services/test_user_service.py \
		tests/services/test_uow.py

# =================================
# 黄金库 CI 绑定（55432）
# =================================
.PHONY: test-phase2p9-core
test-phase2p9-core: venv
	@echo ">>> Running phase2p9 core tests on $(TEST_DB_DSN)"
	WMS_DATABASE_URL=$(TEST_DB_DSN) \
	WMS_TEST_DATABASE_URL=$(TEST_DB_DSN) \
	PYTHONPATH=. $(PYTEST) -q tests/phase2p9

.PHONY: test-diagnostics-core
test-diagnostics-core: venv
	WMS_DATABASE_URL=$(TEST_DB_DSN) \
	WMS_TEST_DATABASE_URL=$(TEST_DB_DSN) \
	PYTHONPATH=. $(PYTEST) -q \
		tests/api/test_debug_trace_api.py \
		tests/api/test_devconsole_orders_api.py

# =================================
# Backend smoke tests（CI 兼容）
# =================================
.PHONY: test-backend-smoke
test-backend-smoke: dev-reset-test-db audit-all
	@echo "[smoke] Running quick backend smoke tests on DEV_TEST_DB_DSN ($(DEV_TEST_DB_DSN))..."
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" \
	$(PYTEST) -q tests/services/test_store_service.py

# =================================
# Pricing smoke tests（quote + scheme binding + constraints）
# =================================
.PHONY: test-pricing-smoke
test-pricing-smoke: dev-reset-test-db audit-all
	@echo "[pytest] Pricing smoke (quote + recommend + scheme binding + constraints)"
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" \
	$(PYTEST) -q -s \
	  tests/api/test_shipping_quote_calc_api.py \
	  tests/api/test_shipping_quote_recommend_contract.py \
	  tests/api/test_shipping_quote_scheme_warehouses_api.py \
	  tests/api/test_zone_brackets_constraints_and_copy.py \
	  tests/api/test_zone_brackets_matrix_unbound_contract.py \
		  tests/api/test_zone_brackets_matrix_grouped_contract.py
