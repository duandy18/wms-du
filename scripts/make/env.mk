# =================================
# env.mk - 基础与帮助/环境/清理
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
	@echo "  make audit-consistency        - 审计：禁止绕过库存底座（禁止在非底座模块直接 await write_ledger()）"
	@echo "  make audit-all                - 口径 + 一致性双审计"
	@echo "  make seed-opening-ledger-test - 制度化：按 stocks 补齐 opening ledger（用于三账一致性）"
	@echo "  make audit-three-books        - 三账一致性自检（TEST DB 上运行 snapshot + compare）"
	@echo ""
	@echo "  make test                     - pytest（默认跑 wms_test；pytest 后自动补账 + 三账体检）"
	@echo "  make test-core                - 只跑 grp_core"
	@echo "  make test-flow                - 只跑 grp_flow"
	@echo "  make test-snapshot            - 只跑 grp_snapshot"
	@echo "  make test-rbac                - RBAC 测试"
	@echo "  make test-internal-outbound   - 内部出库 Golden Flow E2E"
	@echo "  make test-phase4-routing      - Phase4 routing tests"
	@echo "  make test-all                 - 全量回归（不含三账体检后置步骤）"
	@echo ""
	@echo "  make lint-backend             - pre-commit/ruff"
	@echo ""

.PHONY: venv
venv:
	@test -d $(VENV) || python3 -m venv $(VENV)
	@$(PY) -m pip install -U pip

.PHONY: deps
deps: venv
	@test -f requirements.txt && $(PIP) install -r requirements.txt || echo "[deps] skip"

.PHONY: clean-pyc
clean-pyc:
	@find app -name '__pycache__' -type d -prune -exec rm -rf {} + || true
	@find app -name '*.py[co]' -delete || true

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
