# WMS-DU｜本地优先、三机统一、Docker 兜底、CI 可开可关（Step 7 基线实施方案）

> 目标：三台机器都能“一条命令跑起来”，开发—测试—提交主要在本地闭环完成；GitHub 仅作代码同步与可选体检。

---

## 1) 目标与原则
- **目标**：统一环境、统一命令、快速验证、随时回退。
- **四条原则**：
  1) **本地优先**：一切以 `make quick` 是否通过为准。
  2) **环境统一**：能本机跑就本机跑；有差异就用 Docker 容器化执行。
  3) **CI 极简**：只做“能迁移 + 两条 quick 针刺”，非 Required Check，可随时停用。
  4) **可回退**：任何改动都有“一键回滚/停用”的路径。

---

## 2) 仓库最小改动清单（一次性落地）
新增/更新以下文件：
- `Dockerfile`：python3.12 + `psycopg`/`psql` 客户端。
- `docker-compose.yml`：起 `postgres:14-alpine`（宿主 5433），`app` 容器挂载源码。
- `scripts/wait-for-pg.sh`：等待 PG 健康就绪。
- `Makefile`：统一命令（`up/migrate/quick/smoke/all` + 本地直连 `local.*`）。
- `run.sh`：本地/CI 通用的主入口（`./run.sh all` = up→migrate→quick→smoke）。
- （可选）`.github/workflows/ci.yml`：最简 CI，仅 PR 跑“迁移 + 两条 quick”。

> 下面给出**完整示例**，直接按路径保存即可使用。

---

## 3) 文件内容（可直接落地）

### 3.1 `Dockerfile`
```dockerfile
# python 3.12 + 必要系统依赖（psycopg build, psql 客户端）
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates pkg-config libpq-dev postgresql-client \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

CMD ["bash", "-lc", "sleep infinity"]
```

### 3.2 `docker-compose.yml`
```yaml
version: "3.9"
services:
  db:
    image: postgres:14-alpine
    environment:
      POSTGRES_USER: wms
      POSTGRES_PASSWORD: wms
      POSTGRES_DB: wms
    ports: ["5433:5432"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U wms -d wms"]
      interval: 3s
      timeout: 3s
      retries: 20

  app:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      DATABASE_URL: postgresql+psycopg://wms:wms@db:5432/wms
      PYTHONPATH: /app
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - .:/app
    working_dir: /app
    command: ["bash", "-lc", "sleep infinity"]
```

### 3.3 `scripts/wait-for-pg.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail
H="${1:-db}"; P="${2:-5432}"; U="${3:-wms}"; D="${4:-wms}"
for _ in $(seq 1 60); do
  if pg_isready -h "$H" -p "$P" -U "$U" -d "$D" >/dev/null 2>&1; then exit 0; fi
  sleep 1
done
echo "Postgres not ready after 60s" >&2; exit 2
```
> 赋权：`chmod +x scripts/wait-for-pg.sh`

### 3.4 `Makefile`
```make
PY ?= python
PIP ?= pip

# ---- Docker 驱动（推荐三台机器统一使用） ----
.PHONY: up down sh app test ci
up:
	docker compose up -d --build
	docker compose exec app bash -lc "scripts/wait-for-pg.sh db 5432 wms wms || true"

down:
	docker compose down -v

sh:
	docker compose exec app bash

# ---- DB 迁移 / 测试（在 app 容器内执行） ----
.PHONY: migrate quick smoke all
migrate:
	docker compose exec app bash -lc "alembic upgrade head"

quick:
	docker compose exec app bash -lc "\
	  PYTHONPATH=. pytest -q \
	    tests/quick/test_inbound_pg.py::test_inbound_receive_and_putaway_integrity \
	    tests/quick/test_putaway_pg.py::test_putaway_integrity \
	    -s --maxfail=1"

smoke:
	@if docker compose exec app bash -lc "[ -d tests/smoke ]"; then \
	  docker compose exec app bash -lc "pytest -q tests/smoke -s --maxfail=1"; \
	else \
	  $(MAKE) quick; \
	fi

all: migrate quick smoke

# ---- 非 Docker（可选：本机已装 Python/PG 时直接用） ----
.PHONY: local.migrate local.quick
local.migrate:
	$(PY) -m alembic upgrade head

local.quick:
	PYTHONPATH=. pytest -q tests/quick/test_inbound_pg.py::test_inbound_receive_and_putaway_integrity \
	                  tests/quick/test_putaway_pg.py::test_putaway_integrity -s --maxfail=1
```

### 3.5 `run.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail
CMD="${1:-all}"

case "$CMD" in
  up)        make up ;;
  migrate)   make migrate ;;
  quick)     make quick ;;
  smoke)     make smoke ;;
  all)       make up && make migrate && make quick && make smoke ;;
  *) echo "Usage: ./run.sh [up|migrate|quick|smoke|all]" ; exit 1 ;;
esac
```

### 3.6 `.github/workflows/ci.yml`（可选）
```yaml
name: App CI - Mini

on:
  pull_request: { branches: [ main ] }

jobs:
  mini:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:14-alpine
        env:
          POSTGRES_USER: wms
          POSTGRES_PASSWORD: wms
          POSTGRES_DB: wms
        ports: ["5433:5432"]
        options: >-
          --health-cmd="pg_isready -U wms -d wms"
          --health-interval=5s --health-timeout=5s --health-retries=20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt
      - name: migrate + quick
        env:
          DATABASE_URL: postgresql+psycopg://wms:wms@127.0.0.1:5433/wms
        run: |
          alembic upgrade head
          PYTHONPATH=. pytest -q \
            tests/quick/test_inbound_pg.py::test_inbound_receive_and_putaway_integrity \
            tests/quick/test_putaway_pg.py::test_putaway_integrity \
            -s --maxfail=1
```

---

## 4) 三台机器落地步骤（一次 10 分钟）
```bash
# 0) 克隆
git clone https://github.com/duandy18/wms-du.git && cd wms-du

# 1) 起容器（统一环境）
docker compose up -d --build

# 2) 等 PG 就绪（脚本兜底）
docker compose exec app bash -lc "scripts/wait-for-pg.sh db 5432 wms wms || true"

# 3) 迁移 & 快测（本地针刺）
make migrate
make quick        # 两条主链：Inbound + Putaway
# 有需要再跑 smoke（存在 tests/smoke 就跑，否则回退到 quick）
make smoke
```
**判定：** 只要 `make quick` 绿，这台机器就是“就绪可开发”。

---

## 5) 日常开发流程（本地闭环）
1) 改代码 → `make quick`（≤10s 出结论，红就立刻修）。
2) 需要重置环境 → `docker compose down -v && docker compose up -d --build && make migrate`。
3) 提交 & 同步：
```bash
git add -A
pre-commit run -a || true
git commit -m "feat: <描述>"
git push -u origin <你的分支>
```
4) 换机器继续：重复「第4章」三步。

---

## 6) CI 策略（可开可关）
- **默认**：开启一个极简 CI（仅 PR 触发），两步：
  1) `alembic upgrade head`
  2) 跑两条 quick：Inbound/Putaway 针刺
- **不是 Required Check**：红也能合并，CI 仅作“远程复读机”。
- **想停就停**：GitHub Settings → Actions 关闭；随开随用不影响本地节奏。

---

## 7) 分支与合并
- 个人开发：`chore/*`、`feat/*` 分支开发，`git push` 同步。
- 合并主线：本地 `make quick` 绿 → 开 PR；CI 绿/红都不阻拦，主要看本地结论。
- 回滚策略：主线有问题就 `git revert <commit>`；数据库用 Alembic 回退 `alembic downgrade -1`（或 `base`）。

---

## 8) 常见差异与兜底
| 问题 | 解决 |
|---|---|
| 三台机器 Python/psycopg 不一致 | 统一走 Docker 执行（`make ...` 都是容器内命令）。 |
| 5433 被占用 | 改 `docker-compose.yml` 端口映射（如 `5434:5432`），并同步 `DATABASE_URL`。 |
| CI 慢或不稳定 | 暂时关闭 Actions；本地用 Docker 环境复现即可。 |
| 迁移失败/多头 | 本地 `alembic downgrade base && alembic upgrade head`；必要时清空 volume 重来。 |

---

## 9) 验收标准（自检清单）
- [ ] 任意一台机器：`make all` 能跑通；
- [ ] 改任意模块：`make quick` ≤10s 出红绿；
- [ ] 换机器只需三步：`docker compose up -d` → `make migrate` → `make quick`；
- [ ] CI 不是门槛：开着时自动跑“迁移+quick”，关掉不影响开发。

---

## 10) 一次性提交命令块（落地这些 DevOps 文件）
```bash
git add Dockerfile docker-compose.yml scripts/wait-for-pg.sh Makefile run.sh .github/workflows/ci.yml
git commit -m "devops: local-first workflow (dockerized) + mini CI (migrate + quick)"
git push -u origin chore/local-first
```

> 备注：如需把 `.github/workflows/ci.yml` 暂不启用，可先不提交该文件；等需要远程体检时再开启。
