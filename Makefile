SHELL := /bin/bash

.PHONY: up down logs sh test clean-sqlite test-sqlite test-mysql test-pg ci all-tests

# ------------------- Docker Compose -------------------

up:
	docker compose -f ops/compose/docker-compose.dev.yml up -d --build

down:
	docker compose -f ops/compose/docker-compose.dev.yml down

logs:
	docker compose -f ops/compose/docker-compose.dev.yml logs -f --tail=100

sh:
	docker compose -f ops/compose/docker-compose.dev.yml exec api bash

# ------------------- Local Tests -------------------

# 快速测试（不保证数据库一致性）
test:
	pytest -q --maxfail=1 --disable-warnings

# 清理 SQLite 文件
clean-sqlite:
	@set -a; source .env.ci; set +a; \
	if [[ "$$DATABASE_URL" == sqlite:* ]]; then \
	  db_path="$${DATABASE_URL#sqlite:///}"; \
	  [[ "$$db_path" == ./* ]] && db_path="$${db_path#./}"; \
	  rm -f "$$db_path"; \
	  echo "[clean] removed sqlite db: $$db_path"; \
	else \
	  echo "[clean] skip, not sqlite: $$DATABASE_URL"; \
	fi

# 使用 SQLite + .env.ci
test-sqlite: clean-sqlite
	set -a && source .env.ci && set +a; \
	export DATABASE_URL="$$DATABASE_URL"; \
	pytest -q --maxfail=1 --disable-warnings

# 使用 MySQL + .env.ci
test-mysql:
	set -a && source .env.ci && set +a; \
	export DATABASE_URL="mysql+pymysql://$${MYSQL_USER}:$${MYSQL_PASSWORD}@$${MYSQL_HOST}:$${MYSQL_PORT}/$${MYSQL_DB}?charset=utf8mb4"; \
	pytest -q --maxfail=1 --disable-warnings

# 使用 Postgres + .env.ci
test-pg:
	set -a && source .env.ci && set +a; \
	export DATABASE_URL="postgresql+psycopg://$${PGUSER}:$${PGPASSWORD}@$${PGHOST}:$${PGPORT}/$${PGDATABASE}"; \
	pytest -q --maxfail=1 --disable-warnings

# ------------------- CI Simulation -------------------

ci:
	set -a && source .env.ci && set +a; \
	ruff check . && ruff format --check . && black --check . && isort --check-only .; \
	mypy .; \
	export DATABASE_URL="$$DATABASE_URL"; \
	pytest --cov=app --cov-report=term-missing --cov-fail-under=65 -q --maxfail=1 --disable-warnings

# ------------------- Composite -------------------

# 一次性跑三套：SQLite -> MySQL -> Postgres（任一失败即停止）
all-tests:
	@echo "======================[ 1/3 SQLite tests ]======================"
	$(MAKE) test-sqlite
	@echo "======================[ 2/3 MySQL tests ]======================="
	$(MAKE) test-mysql
	@echo "======================[ 3/3 Postgres tests ]===================="
	$(MAKE) test-pg
	@echo "======================[   ALL PASSED   ]========================"
