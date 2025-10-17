# ===== WMS-DU Makefile (no-tab version) =====
# 使用自定义配方前缀，避免必须用 Tab 缩进
.RECIPEPREFIX := >

.PHONY: help venv fmt lint test quick quick-snapshot quick-stock-query quick-outbound-atomic docker-up docker-down

help:
> @echo "Targets:"
> @echo "  fmt                  - ruff + black"
> @echo "  lint                 - ruff check"
> @echo "  test                 - pytest 全量"
> @echo "  quick                - pytest tests/quick"
> @echo "  quick-snapshot       - 仅跑快照分页/搜索针刺"
> @echo "  quick-stock-query    - 仅跑 /stock/query 针刺"
> @echo "  quick-outbound-atomic- 仅跑出库原子模式针刺"
> @echo "  docker-up            - 本地起 PG:14（5433）"
> @echo "  docker-down          - 停 PG 容器"

venv:
> python -m venv .venv

fmt:
> ruff check --fix .
> black .

lint:
> ruff check .

test:
> pytest -q -s

quick:
> pytest -q -s tests/quick

quick-snapshot:
> pytest -q -s tests/quick/test_snapshot_inventory_pg.py

quick-stock-query:
> pytest -q -s tests/quick/test_stock_query_pg.py

quick-outbound-atomic:
> OUTBOUND_ATOMIC=true pytest -q -s tests/quick/test_outbound_atomic_pg.py

docker-up:
> docker run -d --name wms-pg -e POSTGRES_USER=wms -e POSTGRES_PASSWORD=wms -e POSTGRES_DB=wms -p 5433:5432 postgres:14-alpine
> sleep 3
> @echo "DATABASE_URL=postgresql+psycopg://wms:wms@127.0.0.1:5433/wms"   # pragma: allowlist secret

docker-down:
> -docker rm -f wms-pg
