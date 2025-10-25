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
DB_HOST           ?= 127.0.0.1
DB_PORT           ?= 5433
DB_NAME           ?= wms
DB_USER           ?= wms
API_BASE          ?= http://127.0.0.1:$(API_HOST_PORT)

# ================================================================
# 核心编排
# ================================================================

.PHONY: up down ps restart rebuild logs api-logs worker-logs prom-logs grafana-logs

up:
	@echo ">>> 启动本地开发栈"
	$(DC) up -d

down:
	@echo ">>> 停止并清理容器（不删数据卷）"
	$(DC) down

ps:
	$(DC) ps

restart:
	$(DC) restart api worker

rebuild:
	$(DC) build api worker

logs:
	$(DC) logs -f

api-logs:
	$(DC) logs -f api

worker-logs:
	$(DC) logs -f worker

prom-logs:
	$(DC) logs -f prometheus

grafana-logs:
	$(DC) logs -f grafana

# ================================================================
# 测试分层
# ================================================================

.PHONY: quick smoke test

quick:
	@echo ">>> 运行状态机针刺（tests/quick/test_platform_state_machine_pg.py）"
	API_BASE=$(API_BASE) PYTHONPATH=. pytest -q tests/quick/test_platform_state_machine_pg.py -s

smoke:
	@echo ">>> 指标冒烟（tests/smoke/test_monitor_metrics_pg.py）"
	API_BASE=$(API_BASE) PYTHONPATH=. pytest -q tests/smoke/test_monitor_metrics_pg.py -s

# 用法：make test T=tests/xxx::case_name
test:
	@echo ">>> 按路径/用例名运行单测：$(T)"
	@if [ -z "$(T)" ]; then echo "缺少 T= 参数"; exit 2; fi
	API_BASE=$(API_BASE) PYTHONPATH=. pytest -q $(T) -s

# ================================================================
# 运维辅助
# ================================================================

.PHONY: doctor

doctor:
	@echo ">>> 端口占用检查：API=$(API_HOST_PORT), Redis=$(REDIS_HOST_PORT), Prom=$(PROM_HOST_PORT), Grafana=$(GRAFANA_HOST_PORT)"
	@if [ -x scripts/ports_doctor.sh ]; then \
	  scripts/ports_doctor.sh; \
	else \
	  echo "scripts/ports_doctor.sh 不存在或不可执行；生成一个最小版本..."; \
	  mkdir -p scripts; \
	  printf '#!/usr/bin/env bash\nset -euo pipefail\nports=($(API_HOST_PORT) $(REDIS_HOST_PORT) $(PROM_HOST_PORT) $(GRAFANA_HOST_PORT))\nnames=(API REDIS PROM GRAFANA)\nfor i in $${!ports[@]}; do p=$${ports[$$i]}; n=$${names[$$i]}; if ss -lnt | awk "{print \$$4}" | grep -q ":$$p$$"; then echo "[占用] $$n 端口 $$p 正被占用"; else echo "[空闲] $$n 端口 $$p 空闲"; fi; done\n' > scripts/ports_doctor.sh; \
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

# ================================================================
# Phase 2.8 Observability & Replay
# ================================================================

# 复合 Compose（dev + override）
OBS_OVERRIDE_FILE ?= docker-compose.override.yml
DCO := docker compose -f $(COMPOSE_FILE) -f $(OBS_OVERRIDE_FILE)

.PHONY: obs-up obs-down traces replay consistency dashboards

obs-up:
	@echo ">>> 启动 OTel Collector / Jaeger / Exporters / Alertmanager"
	@if [ ! -f "$(OBS_OVERRIDE_FILE)" ]; then \
		echo "[提示] $(OBS_OVERRIDE_FILE) 未找到，请在仓库根添加 Phase 2.8 的 override 文件"; \
		exit 1; \
	fi
	$(DCO) up -d otel-collector jaeger redis-exporter celery-exporter alertmanager
	@echo "Jaeger:       http://localhost:16686"
	@echo "Exporters:    redis-exporter:9121  celery-exporter:9808"
	@echo "Alertmanager: http://localhost:9093"

obs-down:
	@echo ">>> 停止 Phase 2.8 可观测性组件"
	@if [ ! -f "$(OBS_OVERRIDE_FILE)" ]; then \
		echo "[提示] $(OBS_OVERRIDE_FILE) 未找到"; \
		exit 0; \
	fi
	$(DCO) rm -sf otel-collector jaeger redis-exporter celery-exporter alertmanager

traces:
	@echo "Open Jaeger UI: http://localhost:16686"

# 用法：make replay TOPIC=<topic> [LIMIT=100]
replay:
	@if [ -z "$$TOPIC" ]; then \
		echo "用法: make replay TOPIC=<topic> [LIMIT=100]"; exit 2; \
	fi
	@DATABASE_URL=$$DATABASE_URL \
		python tools/replay_events.py --topic $$TOPIC --limit $${LIMIT:-100}

# 用法：make consistency ARGS="--auto-fix --no-dry-run"
consistency:
	@DATABASE_URL=$$DATABASE_URL \
		python tools/consistency_check.py $$ARGS

dashboards:
	@echo "Grafana 默认端口: $(GRAFANA_HOST_PORT)；导入 grafana/provisioning/dashboards/*"

# ================================================================
# 帮助
# ================================================================

help:
	@echo "用法：make <target>"
	@echo
	@echo "核心："
	@echo "  make up          启动本地开发栈（API:$(API_HOST_PORT), Redis:$(REDIS_HOST_PORT), Prom:$(PROM_HOST_PORT), Grafana:$(GRAFANA_HOST_PORT)）"
	@echo "  make down        停止并清理容器（不删数据卷）"
	@echo "  make ps          查看容器状态"
	@echo "  make logs        跟随全量日志"
	@echo "  make api-logs    跟随 API 日志"
	@echo "  make worker-logs 跟随 Celery Worker 日志"
	@echo "  make prom-logs   跟随 Prometheus 日志"
	@echo "  make grafana-logs 跟随 Grafana 日志"
	@echo
	@echo "测试："
	@echo "  make quick       运行状态机针刺（tests/quick/test_platform_state_machine_pg.py）"
	@echo "  make smoke       指标冒烟（tests/smoke/test_monitor_metrics_pg.py，API_BASE 固化为 $(API_BASE)）"
	@echo "  make test T=...  按路径/用例名运行单测（例：make test T=tests/quick/test_platform_events_pg.py::test_xxx）"
	@echo
	@echo "运维："
	@echo "  make restart     重启 API 与 Worker"
	@echo "  make rebuild     重新 build API 与 Worker"
	@echo "  make doctor      端口占用检查（调用 scripts/ports_doctor.sh）"
	@echo
	@echo "可观测性与重放："
	@echo "  make obs-up      启动 OTel Collector / Jaeger / Exporters / Alertmanager（需要 docker-compose.override.yml）"
	@echo "  make obs-down    停止上述可观测性组件"
	@echo "  make traces      打开 Jaeger UI 链接提示"
	@echo "  make replay TOPIC=<topic> [LIMIT=100]  重放事件（tools/replay_events.py）"
	@echo "  make consistency ARGS=\"--auto-fix --no-dry-run\"  对齐快照与台账（tools/consistency_check.py）"
	@echo
	@echo "当前固定端口：API=$(API_HOST_PORT), REDIS=$(REDIS_HOST_PORT), PROM=$(PROM_HOST_PORT), GRAFANA=$(GRAFANA_HOST_PORT)"
	@echo "外部数据库：  $(DB_HOST):$(DB_PORT)  ($(DB_NAME)/$(DB_USER))"

#
