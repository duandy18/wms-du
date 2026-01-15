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

.PHONY: audit-all
audit-all: audit-uom audit-consistency
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
# - 支持定位参数：REF / TRACE_ID / IGNORE_OPENING / LIMIT
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
