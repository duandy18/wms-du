# ==============================
#   WMS-DU Makefile (Full Replacement with .env.local autoload)
# ==============================

SHELL := /bin/bash
VENV  := .venv
PY    := $(VENV)/bin/python
PIP   := $(VENV)/bin/pip
ALEMB := $(PY) -m alembic
PYTEST:= $(VENV)/bin/pytest

# ========================
# Test DSN （中试黄金库）
# ========================
TEST_DB_DSN := postgresql+psycopg://postgres:wms@127.0.0.1:55432/postgres

# 本地 dev 库 DSN（5433）
DEV_DB_DSN  := postgresql+psycopg://wms:wms@127.0.0.1:5433/wms

# ✅ 本地独立测试库 DSN（5433）—— pytest 默认只允许跑在这里，避免误伤 DEV_DB_DSN
DEV_TEST_DB_DSN := postgresql+psycopg://wms:wms@127.0.0.1:5433/wms_test

# ---- 自动加载 .env.local ----
ifneq (,$(wildcard .env.local))
include .env.local
endif

# =================================
# 基础与帮助
# =================================
.PHONY: help
help:
	@echo ""
	@echo "WMS-DU Makefile 帮助："
	@echo "  make venv                     - 创建虚拟环境"
	@echo "  make deps                     - 安装依赖"
	@echo "  make clean-pyc                - 清缓存"
	@echo "  make alembic-check            - alembic check (默认 DEV 5433)"
	@echo "  make upgrade-head             - alembic 升级到 HEAD (默认 DEV 5433)"
	@echo "  make alembic-current-dev      - 查看当前 DEV 库 revision（5433）"
	@echo "  make alembic-history-dev      - 查看 DEV 库最近迁移历史（tail 30）"
	@echo ""
	@echo "  make dev-reset-db             - 重置 5433 开发库（慎用，核爆）"
	@echo "  make dev-reset-test-db        - 重置 5433 测试库 wms_test（推荐，pytest 使用）"
	@echo "  make dev-ensure-admin         - 在 5433 开发库添加 admin/admin123"
	@echo "  make pilot-ensure-admin       - 在 55432 中试库添加 admin（自定义密码）"
	@echo ""
	@echo "  make audit-uom                - 审计：services 层禁止散落 qty_ordered * units_per_case（仅允许 qty_base.py）"
	@echo "  make test                     - pytest（默认跑 wms_test；支持 TESTS=... 指定文件）"
	@echo "  make test-rbac                - 只跑 RBAC 相关测试（test_user_api.py）"
	@echo "  make test-internal-outbound   - 测内部出库 Golden Flow E2E"
	@echo "  make test-pricing-smoke       - 计价系统 smoke（quote + unique + copy）"
	@echo ""

.PHONY: venv
venv:
	@test -d $(VENV) || python3 -m venv $(VENV)
	@$(PY) -m pip install -U pip

.PHONY: deps
deps: venv
	@test -f requirements.txt && $(PIP) install -r requirements.txt || echo "[deps] skip"

# =================================
# Alembic / DB
# =================================
# ✅ 关键原则：
# - 通用目标（upgrade-head / alembic-check / downgrade-base / revision-auto）
#   默认绑定 DEV_DB_DSN，避免误跑到 TEST/PILOT。
# - pytest 默认绑定 DEV_TEST_DB_DSN（wms_test），避免误伤 DEV_DB_DSN（wms）。
# - 若你需要跑别的库，请使用 upgrade-test/check-test 或显式覆写 WMS_DATABASE_URL。

.PHONY: alembic-check
alembic-check: venv
	@echo ">>> Alembic check on DEV_DB_DSN ($(DEV_DB_DSN))"
	@WMS_DATABASE_URL="$(DEV_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_DB_DSN)" $(ALEMB) check

.PHONY: upgrade-head
upgrade-head: venv
	@echo ">>> Alembic upgrade head on DEV_DB_DSN ($(DEV_DB_DSN))"
	@WMS_DATABASE_URL="$(DEV_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_DB_DSN)" $(ALEMB) upgrade head

.PHONY: downgrade-base
downgrade-base: venv
	@echo ">>> Alembic downgrade base on DEV_DB_DSN ($(DEV_DB_DSN))"
	@WMS_DATABASE_URL="$(DEV_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_DB_DSN)" $(ALEMB) downgrade base

.PHONY: revision-auto
revision-auto: venv
	@echo ">>> Alembic revision --autogenerate (DEV_DB_DSN=$(DEV_DB_DSN))"
	@WMS_DATABASE_URL="$(DEV_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_DB_DSN)" $(ALEMB) revision --autogenerate -m "auto"

# ✅ 固化：查 current/history（DEV 5433），避免手敲 env 前缀连错库
.PHONY: alembic-current-dev alembic-history-dev
alembic-current-dev: venv
	@echo ">>> Alembic current on DEV_DB_DSN ($(DEV_DB_DSN))"
	@WMS_DATABASE_URL="$(DEV_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_DB_DSN)" $(ALEMB) current

alembic-history-dev: venv
	@echo ">>> Alembic history (tail 30) on DEV_DB_DSN ($(DEV_DB_DSN))"
	@WMS_DATABASE_URL="$(DEV_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_DB_DSN)" $(ALEMB) history | tail -n 30

# ==========================================
# Dev / Pilot DB Helpers（新增自动种 admin）
# ==========================================

.PHONY: dev-reset-db dev-reset-test-db dev-ensure-admin pilot-ensure-admin

dev-reset-db: venv
	@echo "!!! DANGER: DROP & RECREATE dev DB on 5433/wms !!!"
	@PGPASSWORD="$${PGPASSWORD:-}" psql -h 127.0.0.1 -p 5433 -U wms postgres -c "DROP DATABASE IF EXISTS wms;"
	@PGPASSWORD="$${PGPASSWORD:-}" psql -h 127.0.0.1 -p 5433 -U wms postgres -c "CREATE DATABASE wms;"
	WMS_DATABASE_URL="$(DEV_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_DB_DSN)" $(ALEMB) upgrade head
	@echo "[dev-reset-db] Done."

dev-reset-test-db: venv
	@echo "[dev-reset-test-db] DROP & RECREATE test DB on 5433/wms_test ..."
	@PGPASSWORD="$${PGPASSWORD:-}" psql -h 127.0.0.1 -p 5433 -U wms postgres -c "DROP DATABASE IF EXISTS wms_test;"
	@PGPASSWORD="$${PGPASSWORD:-}" psql -h 127.0.0.1 -p 5433 -U wms postgres -c "CREATE DATABASE wms_test;"
	WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" $(ALEMB) upgrade head
	@echo "[dev-reset-test-db] Done."

dev-ensure-admin: venv
	@echo "[dev-ensure-admin] Ensuring admin on DEV (5433/wms)..."
	WMS_DATABASE_URL="$(DEV_DB_DSN)" \
	ADMIN_USERNAME="admin" \
	ADMIN_PASSWORD="admin123" \
	ADMIN_FULL_NAME="Dev Admin" \
	$(PY) scripts/ensure_admin.py

pilot-ensure-admin: venv
	@echo "[pilot-ensure-admin] Ensuring admin on PILOT ($(TEST_DB_DSN))..."
	WMS_DATABASE_URL="$(TEST_DB_DSN)" \
	ADMIN_USERNAME="admin" \
	ADMIN_PASSWORD="$(or $(PILOT_ADMIN_PASSWORD),Pilot-Admin-Strong-Password)" \
	ADMIN_FULL_NAME="Pilot Admin" \
	$(PY) scripts/ensure_admin.py

# =================================
# 清理
# =================================
.PHONY: clean-pyc
clean-pyc:
	@find app -name '__pycache__' -type d -prune -exec rm -rf {} + || true
	@find app -name '*.py[co]' -delete || true

# Day-0：体检
.PHONY: day0
day0: clean-pyc alembic-check
	@echo 'Day-0 done.'

# =================================
# 分组标记注入（A + C）
# =================================
.PHONY: mark-ac
mark-ac:
	@bash -c 'set -euo pipefail; \
	  apply_mark() { \
	    local mark="$$1"; shift; \
	    for f in "$$@"; do \
	      if [ -f "$$f" ] && ! rg -q "pytestmark" "$$f"; then \
	        sed -i "1i import pytest\npytestmark = pytest.mark.$$mark\n" "$$f"; \
	        echo "[mark] added $$mark -> $$f"; \
	      fi; \
	    done; \
	  }; \
	  apply_mark grp_core \
	    tests/services/test_inbound_service.py \
	    tests/services/test_putaway_service.py \
	    tests/services/test_outbound_service.py \
	    tests/services/test_inventory_ops.py; \
	  apply_mark grp_flow \
	    tests/services/test_outbound_fefo_basic.py \
	    tests/services/test_outbound_ledger_consistency.py \
	    tests/services/test_stock_service_fefo.py;'

# =================================
# 口径审计：禁止散落乘法（Phase 2 硬规则）
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

# =================================
# 核心测试
# =================================
.PHONY: test-core
test-core: venv
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" $(PYTEST) -q -m grp_core -s

.PHONY: test-flow
test-flow: venv
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" $(PYTEST) -q -m grp_flow -s

.PHONY: test-snapshot
test-snapshot: venv
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" $(PYTEST) -q -m grp_snapshot -s

# ---------------------------------
# 通用 pytest 入口（支持 TESTS=...）
# ---------------------------------
.PHONY: test
test: venv
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

# ---------------------------------
# RBAC 专用测试入口
# ---------------------------------
.PHONY: test-rbac
test-rbac: venv
	@echo "[pytest] RBAC tests – tests/api/test_user_api.py"
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" \
	$(PYTEST) -q -s tests/api/test_user_api.py

# ---------------------------------
# Internal Outbound 单元测试入口
# ---------------------------------
.PHONY: test-internal-outbound
test-internal-outbound: venv
	@echo "[pytest] Internal Outbound Golden Flow E2E"
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" \
	$(PYTEST) -q -s tests/services/test_internal_outbound_service.py

# =================================
# Phase 4：Routing 测试线
# =================================
.PHONY: test-phase4-routing
test-phase4-routing: venv
	@echo "[pytest] Phase 4 routing tests"
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" \
	$(PYTEST) -q \
		tests/services/test_order_service_phase4_routing.py \
		tests/services/test_order_route_mode_phase4.py \
		tests/services/test_order_trace_phase4_routing.py

# =================================
# 全量回归
# =================================
.PHONY: test-all
test-all: venv
	@echo "[pytest] Running full test suite on DEV_TEST_DB_DSN ($(DEV_TEST_DB_DSN))"
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" $(PYTEST) -q

# =================================
# 核心服务 CRUD/UoW
# =================================
.PHONY: test-svc-core
test-svc-core: venv
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
# 双库策略：DEV（5433） vs TEST/PILOT（55432）
# =================================
.PHONY: upgrade-dev upgrade-test check-dev check-test

upgrade-dev: venv
	@echo ">>> Alembic upgrade head on DEV_DB_DSN ($(DEV_DB_DSN))"
	WMS_DATABASE_URL="$(DEV_DB_DSN)" \
	WMS_TEST_DATABASE_URL="$(DEV_DB_DSN)" \
	$(ALEMB) upgrade head

upgrade-test: venv
	@echo ">>> Alembic upgrade head on TEST_DB_DSN ($(TEST_DB_DSN))"
	WMS_DATABASE_URL="$(TEST_DB_DSN)" \
	WMS_TEST_DATABASE_URL="$(TEST_DB_DSN)" \
	$(ALEMB) upgrade head

check-dev: venv
	@echo ">>> Alembic check on DEV_DB_DSN ($(DEV_DB_DSN))"
	WMS_DATABASE_URL="$(DEV_DB_DSN)" \
	WMS_TEST_DATABASE_URL="$(DEV_DB_DSN)" \
	$(ALEMB) check

check-test: venv
	@echo ">>> Alembic check on TEST_DB_DSN ($(TEST_DB_DSN))"
	WMS_DATABASE_URL="$(TEST_DB_DSN)" \
	WMS_TEST_DATABASE_URL="$(TEST_DB_DSN)" \
	$(ALEMB) check

# =================================
# Pilot DB 备份（在中试服务器上运行）
# =================================
.PHONY: backup-pilot-db
backup-pilot-db:
	@bash scripts/backup_pilot_db.sh

# =================================
# Lint backend（CI 调用 pre-commit）
# =================================
.PHONY: lint-backend
lint-backend:
	@echo "[lint] Running ruff via pre-commit ..."
	pre-commit run --all-files

# =================================
# Backend smoke tests（CI 兼容）
# =================================
.PHONY: test-backend-smoke
test-backend-smoke: dev-reset-test-db
	@echo "[smoke] Running quick backend smoke tests on DEV_TEST_DB_DSN ($(DEV_TEST_DB_DSN))..."
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" \
	$(PYTEST) -q tests/services/test_store_service.py

# =================================
# Pricing smoke tests（quote + unique + copy）
# =================================
.PHONY: test-pricing-smoke
test-pricing-smoke: dev-reset-test-db
	@echo "[pytest] Pricing smoke (quote + unique + copy)"
	@PYTHONPATH=. WMS_DATABASE_URL="$(DEV_TEST_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_TEST_DB_DSN)" \
	$(PYTEST) -q -s \
	  tests/api/test_shipping_quote_pricing_api.py \
	  tests/api/test_zone_brackets_constraints_and_copy.py
