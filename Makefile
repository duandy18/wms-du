# =========================
# WMS-DU · Makefile (dev)
# 固化端口/环境，提供一键启停与分层测试
# =========================

SHELL := /bin/bash

# -------- 路径与 Compose 文件 --------
COMPOSE_DIR   := ops/compose
COMPOSE_FILE  := $(COMPOSE_DIR)/docker-compose.dev.yml
DC            := docker compose -f $(COMPOSE_FILE)

# -------- 固化端口（默认值；也可在 ops/compose/.env 中覆盖） --------
API_HOST_PORT     ?= 8001
PROM_HOST_PORT    ?= 9090
GRAFANA_HOST_PORT ?= 3000
REDIS_HOST_PORT   ?= 6379

# -------- 外部数据库（独立容器 wms-du-db@5433） --------
DB_HOST ?= 127.0.0.1
DB_PORT ?= 5433
DB_USER ?= wms
DB_PASS ?= wms
DB_NAME ?= wms

# -------- 本地测试/Producer 与 Worker 对齐的 Redis 配置 --------
export REDIS_URL            := redis://localhost:$(REDIS_HOST_PORT)/0
export CELERY_RESULT_BACKEND:= redis://localhost:$(REDIS_HOST_PORT)/1

# -------- 本地 API 访问地址（我们将 API 宿主口固定在 8001）--------
export API_BASE := http://127.0.0.1:$(API_HOST_PORT)

# -------- DB URL（有些测试/脚本会用到） --------
export DATABASE_URL := postgresql+psycopg://$(DB_USER):$(DB_PASS)@$(DB_HOST):$(DB_PORT)/$(DB_NAME)

# -------- Python 测试命令 --------
PYTEST := pytest -q

# -------- 帮助 --------
.PHONY: help
help:
	@echo "用法：make <target>"
	@echo
	@echo "核心："
	@echo "  make up          启动本地开发栈（API:$(API_HOST_PORT), Redis:$(REDIS_HOST_PORT), Prom:$(PROM_HOST_PORT), Grafana:$(GRAFANA_HOST_PORT)）"
	@echo "  make down        停止并清理容器（不删数据卷）"
	@echo "  make ps          查看容器状态"
	@echo "  make logs        跟随 API 日志"
	@echo "  make api-logs    跟随 API 日志"
	@echo "  make worker-logs 跟随 Celery Worker 日志"
	@echo "  make prom-logs   跟随 Prometheus 日志"
	@echo "  make grafana-logs 跟随 Grafana 日志"
	@echo
	@echo "测试："
	@echo "  make quick       运行状态机针刺（tests/quick/test_platform_state_machine_pg.py）"
	@echo "  make smoke       指标冒烟（tests/smoke/test_monitor_metrics_pg.py，API_BASE 固化为 $(API_BASE)）"
	@echo "  make test T=path::case  按路径/用例名运行单测（例如：make test T=tests/quick/test_platform_events_pg.py::test_xxx）"
	@echo
	@echo "运维："
	@echo "  make restart     重启 API 与 Worker"
	@echo "  make rebuild     重新 build API 与 Worker"
	@echo "  make doctor      端口占用检查（调用 scripts/ports_doctor.sh）"
	@echo
	@echo "当前固定端口：API=$(API_HOST_PORT), REDIS=$(REDIS_HOST_PORT), PROM=$(PROM_HOST_PORT), GRAFANA=$(GRAFANA_HOST_PORT)"
	@echo "外部数据库：  $(DB_HOST):$(DB_PORT)  ($(DB_NAME)/$(DB_USER))"

# -------- Compose 控制 --------
.PHONY: up down ps restart rebuild
up:
	cd $(COMPOSE_DIR) && $(DC) up -d --remove-orphans

down:
	cd $(COMPOSE_DIR) && $(DC) down

ps:
	cd $(COMPOSE_DIR) && $(DC) ps

restart:
	cd $(COMPOSE_DIR) && $(DC) up -d api celery-worker

rebuild:
	cd $(COMPOSE_DIR) && $(DC) build api celery-worker
	cd $(COMPOSE_DIR) && $(DC) up -d api celery-worker

# -------- 日志 --------
.PHONY: logs api-logs worker-logs prom-logs grafana-logs
logs: api-logs

api-logs:
	docker logs -f wms-api

worker-logs:
	docker logs -f wms-celery

prom-logs:
	docker logs -f wms-prometheus

grafana-logs:
	docker logs -f wms-grafana

# -------- 测试分层 --------
.PHONY: quick smoke test
quick:
	$(PYTEST) tests/quick/test_platform_state_machine_pg.py -s

smoke:
	# API_BASE 固化为 $(API_BASE) ，避免端口漂移导致 8000/8001 错打
	API_BASE=$(API_BASE) $(PYTEST) tests/smoke/test_monitor_metrics_pg.py -s

# 任意路径/用例（用法：make test T=tests/quick/test_platform_events_pg.py::test_xxx）
test:
	@if [ -z "$(T)" ]; then echo "用法：make test T=tests/xxx.py[::case]"; exit 1; fi
	API_BASE=$(API_BASE) $(PYTEST) $(T) -s

# -------- 运维小工具 --------
.PHONY: doctor
doctor:
	@if [ -x "scripts/ports_doctor.sh" ]; then \
	  scripts/ports_doctor.sh; \
	else \
	  echo "scripts/ports_doctor.sh 不存在或不可执行；生成一个最小版本..."; \
	  mkdir -p scripts; \
	  printf '#!/usr/bin/env bash\nset -euo pipefail\nports=($(API_HOST_PORT) $(PROM_HOST_PORT) $(GRAFANA_HOST_PORT) $(REDIS_HOST_PORT) 5433)\nnames=(API Prometheus Grafana Redis Postgres)\nfor i in $${!ports[@]}; do p=$${ports[$$i]}; n=$${names[$$i]}; if sudo lsof -iTCP:$$p -sTCP:LISTEN -nP >/dev/null 2>&1; then echo "[占用] $$n 端口 $$p："; sudo lsof -iTCP:$$p -sTCP:LISTEN -nP || true; docker ps --format "table {{.ID}}\t{{.Names}}\t{{.Ports}}" | grep -E ":$$p->|:$$p " || true; echo; else echo "[空闲] $$n 端口 $$p 空闲"; fi; done\n' > scripts/ports_doctor.sh; \
	  chmod +x scripts/ports_doctor.sh; \
	  scripts/ports_doctor.sh; \
	fi
# ================================================================
# Git 辅助工具
# ================================================================

.PHONY: safe-add
safe-add:
	@echo ">>> 运行安全 add (过滤调试/临时文件)"
	@bash scripts/safe-add.sh
