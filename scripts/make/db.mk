# =================================
# db.mk - Alembic / DB helpers
# =================================

# ✅ 关键原则：
# - 通用目标默认绑定 DEV_DB_DSN，避免误跑到 TEST/PILOT。
# - pytest 默认绑定 DEV_TEST_DB_DSN（wms_test），避免误伤 DEV_DB_DSN（wms）。

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

.PHONY: alembic-current-dev alembic-history-dev
alembic-current-dev: venv
	@echo ">>> Alembic current on DEV_DB_DSN ($(DEV_DB_DSN))"
	@WMS_DATABASE_URL="$(DEV_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_DB_DSN)" $(ALEMB) current

alembic-history-dev: venv
	@echo ">>> Alembic history (tail 30) on DEV_DB_DSN ($(DEV_DB_DSN))"
	@WMS_DATABASE_URL="$(DEV_DB_DSN)" WMS_TEST_DATABASE_URL="$(DEV_DB_DSN)" $(ALEMB) history | tail -n 30

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
