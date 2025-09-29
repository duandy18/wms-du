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
# 一键提交并推送到 feat/rbac-lite 分支
push-rbac:
	@git add .
	@git commit -m "chore: auto push from make push-rbac" || echo "⚠️ Nothing to commit"
	@git push origin feat/rbac-lite
# 一键拉取远端最新的 feat/rbac-lite
pull-rbac:
	@git fetch origin
	@git checkout feat/rbac-lite
	@git pull origin feat/rbac-lite
# 一键启动开发环境
dev:
	@echo "🔎 清理端口 8000..."
	@PIDS=$$(lsof -ti :8000 || true); \
	if [ -n "$$PIDS" ]; then \
		echo "⚡ 杀掉进程 $$PIDS"; \
		kill -9 $$PIDS; \
	fi
	@echo "🚀 启动 uvicorn ..."
	@uvicorn app.main:app --reload --port 8000 > uvicorn.log 2>&1 & echo $$! > uvicorn.pid
	@echo "✅ 已启动 (PID=$$(cat uvicorn.pid))，日志写入 uvicorn.log"
	@tail -n 20 -f uvicorn.log
