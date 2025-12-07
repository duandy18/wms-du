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

# ---- 自动加载 .env.local 环境（仅用于 Makefile 变量，不强制 export）----
# 说明：
#   - include .env.local 可以让你在 Make 里用 $(FOO) 这些变量；
#   - 不再 export 全量变量，避免 DATABASE_URL= 这类空值覆盖测试用 URL。
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
	@echo "  make venv                     - 创建虚拟环境并升级 pip"
	@echo "  make deps                     - 安装依赖 (requirements.txt)"
	@echo "  make clean-pyc                - 清理 __pycache__ 和 *.py[co]"
	@echo "  make alembic-check            - 结构一致性检测 (alembic check)"
	@echo "  make upgrade-head             - alembic 升级到 HEAD（默认 55432 黄金库）"
	@echo "  make day0                     - Day-0 体检 (clean-pyc + alembic-check)"
	@echo "  make mark-ac                  - 为 A/C 组测试注入 pytest 标记(如无则添加)"
	@echo "  make test-core                - 运行 grp_core（A组：核心服务）"
	@echo "  make test-flow                - 运行 grp_flow（C组：FEFO/出库分配）"
	@echo "  make test-snapshot            - 运行 grp_snapshot（D组相关视图/三账）"
	@echo "  make test-routing-metrics     - Phase4 路由观测专用测试组"
	@echo "  make fefo-smoke               - FEFO 最小烟雾（两条关键用例）"
	@echo "  make check-ac                 - 按计划先跑 A + C"
	@echo "  make check-bd                 - 再跑 B + D（约束+三账）"
	@echo "  make gate-structure-fefo      - CI 最小闸门（结构+FEFO烟雾）"
	@echo "  make prepilot                 - 中试前体检：跑 pre_pilot 黄金链路三板斧"
	@echo "  make check                    - 兼容旧入口：一键全测(Mini流水)"
	@echo "  make phase0-verify            - 兼容旧入口：Phase0 校验脚本（如存在）"
	@echo "  make lint-backend             - 后端 pre-commit lint（ruff 等）"
	@echo "  make test-backend-quick       - 后端快速回归（少量金丝雀用例）"
	@echo "  make test-backend-smoke       - 后端 v2 烟囱 Smoke 套餐（CI 主闸门）"
	@echo ""
	@echo "  make test-phase2p9-core       - phase2p9 黄金链路（三本账+软预占+生命周期）@ 55432"
	@echo "  make test-diagnostics-core    - DebugTrace + DevConsole Orders 核心用例 @ 55432"
	@echo "  make test-backend-smoke-55432 - 在 55432 黄金库上跑后端 Smoke 套餐"
	@echo ""

.PHONY: venv
venv:
	@test -d $(VENV) || python3 -m venv $(VENV)
	@$(PY) -m pip install -U pip

.PHONY: deps
deps: venv
	@test -f requirements.txt && $(PIP) install -r requirements.txt || echo "[deps] skip: requirements.txt not found"

# =================================
# Alembic / DB
# =================================
.PHONY: alembic-check
alembic-check: venv
	@$(ALEMB) check

.PHONY: upgrade-head
upgrade-head: venv
	@$(ALEMB) upgrade head

.PHONY: downgrade-base
downgrade-base: venv
	@$(ALEMB) downgrade base

.PHONY: revision-auto
revision-auto: venv
	@$(ALEMB) revision --autogenerate -m "auto"

# =================================
# 清理
# =================================
.PHONY: clean-pyc
clean-pyc:
	@find app -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
	@find app -name '*.py[co]' -delete 2>/dev/null || true

# Day-0：体检（清缓存 + 结构一致性）
.PHONY: day0
day0: clean-pyc alembic-check
	@echo 'Day-0 done: cache cleaned & alembic check executed.'

# =================================
# 分组标记注入（A 组 + C 组）
# =================================
# 说明：仅在目标文件未包含 "pytestmark =" 时才插入，避免重复；需要 ripgrep/rg 与 sed。
.PHONY: mark-ac
mark-ac:
	@bash -c 'set -euo pipefail; \
	  apply_mark() { \
	    local mark="$$1"; shift; \
	    for f in "$$@"; do \
	      if [ -f "$$f" ]; then \
	        if ! rg -q "pytestmark\\s*=" "$$f"; then \
	          sed -i "1i import pytest\npytestmark = pytest.mark.$$mark\n" "$$f"; \
	          echo "[mark] added $$mark -> $$f"; \
	        else \
	          echo "[mark] skip (exists) $$f"; \
	        fi; \
	      else \
	        echo "[mark] skip (missing) $$f"; \
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
# 三统一后测试推进（A + C + B + D）
# =================================
.PHONY: test-core
test-core: venv
	@PYTHONPATH=. $(PYTEST) -q -m grp_core -s

.PHONY: test-flow
test-flow: venv
	@PYTHONPATH=. $(PYTEST) -q -m grp_flow -s

.PHONY: test-snapshot
test-snapshot: venv
	@PYTHONPATH=. $(PYTEST) -q -m grp_snapshot -s

# Phase 4：路由指标 + 视图 + 沙盘 专线
.PHONY: test-routing-metrics
test-routing-metrics: venv
	@PYTHONPATH=. $(PYTEST) -q -s \
		tests/services/test_order_service_phase4_routing.py \
		tests/db/test_vw_routing_metrics_daily.py \
		tests/services/test_routing_metrics_emit.py \
		tests/sandbox/test_routing_sandbox_multi_warehouse.py

# FEFO 烟雾闸门（用于本地和 CI 的最小门槛）
.PHONY: fefo-smoke
fefo-smoke: venv
	@set -e; \
	if [ -f tests/services/test_outbound_service.py ]; then \
	  PYTHONPATH=. $(PYTEST) -q -s tests/services/test_outbound_service.py::test_outbound_fefo_basic; \
	else echo "[fefo-smoke] skip: tests/services/test_outbound_service.py not found"; fi; \
	if [ -f tests/services/test_outbound_ledger_consistency.py ]; then \
	  PYTHONPATH=. $(PYTEST) -q -s tests/services/test_outbound_ledger_consistency.py::test_ledger_after_qty_consistency; \
	else echo "[fefo-smoke] skip: tests/services/test_outbound_ledger_consistency.py not found"; fi

# =================================
# Pre-pilot：中试前黄金链路体检
# =================================
.PHONY: prepilot
prepilot: venv
	@echo "[prepilot] running pytest -m pre_pilot ..."
	@PYTHONPATH=. $(PYTEST) -q -m pre_pilot

# A+C 仅验证（优先）
.PHONY: check-ac
check-ac: day0 mark-ac test-core test-flow

# B+D 验证（在 A+C 通过后执行）
.PHONY: check-bd
check-bd: venv
	@set -e; \
	for t in \
	  tests/ci/test_db_invariants.py \
	  tests/alembic/test_migration_contract.py \
	  tests/services/test_stock_integrity.py \
	  tests/quick/test_three_books_pg.py \
	  tests/quick/test_snapshot_inventory_pg.py \
	  tests/services/test_reservation_lifecycle.py \
	; do \
	  if [ -f "$$t" ]; then \
	    echo "[pytest] $$t"; PYTHONPATH=. $(PYTEST) -q -s "$$t"; \
	  else \
	    echo "[pytest] skip: $$t not found"; \
	  fi; \
	done

# CI 最小结构+FEFO 闸门（供分支保护引用）
.PHONY: gate-structure-fefo
gate-structure-fefo: alembic-check fefo-smoke
	@echo 'Structure OK + FEFO smoke passed.'

# =================================
# 兼容：你原有的 Mini 流水 & 校验入口
# =================================
# 说明：这些目标采用“存在性检测”，最大化与历史用法兼容。
.PHONY: test-outbound-mini
test-outbound-mini: venv
	@set -e; \
	if [ -f tests/services/test_outbound_service.py ]; then \
	  PYTHONPATH=. $(PYTEST) -q -s tests/services/test_outbound_service.py::test_outbound_fefo_basic || exit $$?; \
	else echo "[mini] skip outbound: tests/services/test_outbound_service.py not found"; fi

.PHONY: test-platform-mini
test-platform-mini: venv
	@set -e; \
	for f in tests/services/test_platform_adapter.py tests/services/test_platform_events.py; do \
	  if [ -f "$$f" ]; then \
	    echo "[mini] $$f"; PYTHONPATH=. $(PYTEST) -q -s "$$f" || exit $$?; \
	  else \
	    echo "[mini] skip platform: $$f not found"; \
	  fi; \
	done

.PHONY: test-reserve-mini
test-reserve-mini: venv
	@set -e; \
	if [ -f tests/services/test_reservation_lifecycle.py ]; then \
	  PYTHONPATH=. $(PYTEST) -q -s tests/services/test_reservation_lifecycle.py::test_basic_reserve || true; \
	else echo "[mini] skip reserve-mini: tests/services/test_reservation_lifecycle.py not found"; fi

.PHONY: test-reserve-lifecycle
test-reserve-lifecycle: venv
	@set -e; \
	if [ -f tests/services/test_reservation_lifecycle.py ]; then \
	  PYTHONPATH=. $(PYTEST) -q -s tests/services/test_reservation_lifecycle.py; \
	else echo "[mini] skip reserve-lifecycle: tests/services/test_reservation_lifecycle.py not found"; fi

.PHONY: test-metrics-mini
test-metrics-mini: venv
	@set -e; \
	for f in tests/services/test_audit_logger.py tests/services/test_metrics.py; do \
	  if [ -f "$$f" ]; then \
	    echo "[mini] $$f"; PYTHONPATH=. $(PYTEST) -q -s "$$f" || exit $$?; \
	  else \
	    echo "[mini] skip metrics: $$f not found"; \
	  fi; \
	done

# 一键全测 (Mini) —— 保持与历史一致
.PHONY: check
check:
	@$(MAKE) test-outbound-mini
	@$(MAKE) test-platform-mini
	@$(MAKE) test-reserve-mini
	@$(MAKE) test-reserve-lifecycle
	@$(MAKE) test-metrics-mini

# 历史脚本（如存在则执行）
.PHONY: phase0-verify
phase0-verify:
	@if [ -x tools/audits/phase0/verify.sh ]; then \
	  bash tools/audits/phase0/verify.sh; \
	else \
	  echo "[phase0-verify] skip: tools/audits/phase0/verify.sh not found or not executable"; \
	fi

.PHONY: lint-backend test-backend-quick

lint-backend:
	@pre-commit run --all-files

test-backend-quick: venv
	@PYTHONPATH=. $(PYTEST) -q \
		tests/phase2p9/test_fefo_outbound_three_books.py \
		tests/services/test_outbound_sandbox_phase4_routing.py

.PHONY: test-backend-smoke

test-backend-smoke: venv
	@PYTHONPATH=. $(PYTEST) -q \
		tests/quick/test_inbound_smoke_pg.py \
		tests/quick/test_outbound_core_v2.py \
		tests/quick/test_outbound_commit_v2.py \
		tests/quick/test_snapshot_inventory_pg.py \
		tests/phase2p9/test_fefo_outbound_three_books.py \
		tests/services/test_order_lifecycle_v2.py \
		tests/services/test_outbound_e2e_phase4_routing.py \
		tests/smoke/test_platform_events_smoke_pg.py

# =================================
# 黄金库绑定测试线（55432）
# =================================

.PHONY: test-phase2p9-core
test-phase2p9-core: venv
	@echo ">>> Running phase2p9 core tests on $(TEST_DB_DSN)"
	WMS_DATABASE_URL=$(TEST_DB_DSN) \
	WMS_TEST_DATABASE_URL=$(TEST_DB_DSN) \
	PYTHONPATH=. $(PYTEST) -q tests/phase2p9

.PHONY: test-diagnostics-core
test-diagnostics-core: venv
	@echo ">>> Running diagnostics & devconsole tests on $(TEST_DB_DSN)"
	WMS_DATABASE_URL=$(TEST_DB_DSN) \
	WMS_TEST_DATABASE_URL=$(TEST_DB_DSN) \
	PYTHONPATH=. $(PYTEST) -q \
		tests/api/test_debug_trace_api.py \
		tests/api/test_devconsole_orders_api.py

.PHONY: test-backend-smoke-55432
test-backend-smoke-55432: venv
	@echo ">>> Running backend smoke tests on $(TEST_DB_DSN)"
	WMS_DATABASE_URL=$(TEST_DB_DSN) \
	WMS_TEST_DATABASE_URL=$(TEST_DB_DSN) \
	PYTHONPATH=. $(PYTEST) -q \
		tests/quick/test_inbound_smoke_pg.py \
		tests/quick/test_outbound_core_v2.py \
		tests/quick/test_outbound_commit_v2.py \
		tests/quick/test_snapshot_inventory_pg.py \
		tests/phase2p9/test_fefo_outbound_three_books.py \
		tests/services/test_order_lifecycle_v2.py \
		tests/services/test_outbound_e2e_phase4_routing.py \
		tests/smoke/test_platform_events_smoke_pg.py
