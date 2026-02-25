# =================================
# audit.mk - 审计 / 守门员规则
# =================================

.PHONY: audit-no-legacy-stock-sql
audit-no-legacy-stock-sql:
	@bash -c 'set -euo pipefail; \
	  echo "[audit-no-legacy-stock-sql] forbid SQL access to legacy stocks/batches in app/..."; \
	  hits="$$(rg -n --hidden \
	    --glob "!alembic/**" \
	    --glob "!tests/**" \
	    --glob "!**/*.md" \
	    --glob "!**/*.sql" \
	    "(?i)(FROM|JOIN|UPDATE|INTO)\\s+stocks\\b|(?i)(FROM|JOIN|UPDATE|INTO)\\s+batches\\b" app || true)"; \
	  if [ -z "$$hits" ]; then \
	    echo "[audit-no-legacy-stock-sql] OK (no legacy SQL access)"; \
	    exit 0; \
	  fi; \
	  echo ""; \
	  echo "$$hits"; \
	  echo ""; \
	  echo "[audit-no-legacy-stock-sql] FAIL: legacy SQL access detected in app/"; \
	  echo "  use stocks_lot + lots instead (lot-world is the only truth)."; \
	  exit 1;'

# =================================
# 统一 audit 入口
# =================================

.PHONY: audit-all
audit-all: audit-no-legacy-stock-sql
	@echo "[audit-all] OK"
