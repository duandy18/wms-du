# =================================
# lint.mk - backend lint
# =================================

.PHONY: lint-backend
lint-backend:
	@echo "[lint] Running ruff via pre-commit ..."
	pre-commit run --all-files
