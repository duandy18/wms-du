# Phase 2｜Snapshot & Outbound 真接口对接——全链路落地纪要（2025-10-16）

> 本页汇总本聊天全过程的**决策→实现→联调→验证**，沉淀为一页“可复用作业单”。涵盖：后端最小实现（FastAPI + SQLAlchemy + PG）、幂等策略、MSW↔真实 API 开关、CI/quick 测试、排障记录与最终文件清单。

---

## 0. 里程碑结果（TL;DR）
- ✅ **POST /outbound/commit**：幂等（`(ref,item_id,location_id)` 锚点）+ 扣减 stocks + 写台账（`delta<0`、`after_qty`、`occurred_at=NOW()`、`ref_line` 行号）已跑通。
- ✅ **GET /snapshot/inventory**：返回 `{ item_id, name, spec(""), total_qty, top2_locations, earliest_expiry, near_expiry }`，供首页使用。
- ✅ **HTTP & 服务层 quick**：
  - `tests/quick/test_outbound_pg.py`（服务层幂等 + 库存不足）全绿。
  - `tests/quick/test_outbound_http_pg.py`（直打路由 + 并发针刺）全绿。
  - `tests/quick/test_snapshot_inventory_pg.py`（汇总/Top2/到期）全绿。
- ✅ **Makefile** 增强：`make quick` 一次跑 5 条针刺。
- ✅ 前端可通过 `.env` 切至真实 API：`VITE_API_MODE=real`、`VITE_API_BASE=http://127.0.0.1:8000`。

---

## 1. 数据库与迁移
### 1.1 新增幂等锚点表 `outbound_commits`
- 迁移文件：`alembic/versions/20251016_add_outbound_commits.py`
- 结构：
  - `id SERIAL PK`
  - `ref VARCHAR(64) NOT NULL`
  - `item_id INT NOT NULL`
  - `location_id INT NOT NULL`
  - `qty INT NOT NULL`
  - `created_at TIMESTAMPTZ DEFAULT NOW()`
  - `UNIQUE(ref, item_id, location_id)`（`uq_outbound_ref_item_loc`）
- 同步补齐索引：`ix_outbound_commits_ref`、（若缺）`ix_stock_ledger_ref`。

### 1.2 约束口径（与现有表对齐）
- `stock_ledger`：**不存 `location_id`**；必须写入 `stock_id`、`item_id`、`delta`、`after_qty`、`occurred_at`、`reason`、`ref`、`ref_line`。
- `stocks`：`UNIQUE(item_id, location_id)`；扣减使用 `FOR UPDATE` 锁行。
- `batches`：可选参与 `earliest_expiry` 聚合。

---

## 2. 后端实现（关键文件）
- **路由**：
  - `app/api/endpoints/outbound.py`：自适应事务（已在事务 → 用 `begin_nested()`）。
  - `app/api/endpoints/snapshot.py`：新增 `/snapshot/inventory`（返回 `{ items: [...] }`）。
- **服务**：
  - `app/services/outbound_service.py`：
    1) 插入 `outbound_commits`（幂等锚点，`ON CONFLICT DO NOTHING`）；
    2) `SELECT ... FOR UPDATE` 锁定 `stocks` 并读 `before_qty`；
    3) `UPDATE stocks SET qty = after_qty`；
    4) `INSERT stock_ledger(..., after_qty, occurred_at=NOW(), reason='OUTBOUND', ref, ref_line)`；
    5) 返回 `OK / IDEMPOTENT / INSUFFICIENT_STOCK`。
  - `app/services/snapshot_service.py`：
    - `query_inventory_snapshot(session)`：PG/SQLite 双方言 SQL，**不依赖 `items.spec` 列**（统一 `'' AS spec`），聚合 `total_qty / top2 / earliest_expiry / near_expiry`。
    - 兼容模块级代理函数 `query_inventory_snapshot(...)`（旧测试引用）。
- **Schemas**：
  - `app/schemas/outbound.py`：`OutboundCommitRequest/Response`。
  - （沿用现有 `app/schemas/snapshot.py` 并在 API 中直接返回 dict → Pydantic 校验）。

---

## 3. 前端联通
- 环境开关：
  - `.env.development.local`
    ```ini
    VITE_API_MODE=real
    VITE_API_BASE=http://127.0.0.1:8000
    ```
- 调用：
  - `GET /snapshot/inventory` → 首页卡片/表格。
  - `POST /outbound/commit` → 出库提交（重复同 `ref` 返回 `IDEMPOTENT`）。

---

## 4. quick / CI 用例清单
- `tests/quick/test_outbound_pg.py`：服务层幂等；库存不足返回 `INSUFFICIENT_STOCK`；台账仅一条。
- `tests/quick/test_outbound_http_pg.py`：覆盖依赖为**每请求新会话**；并发 `gather` 验证“一条 `OK` + 一条 `IDEMPOTENT`”。
- `tests/quick/test_snapshot_inventory_pg.py`：造数（含 `sku NOT NULL` 约束）；断言 `total_qty`、Top2、`earliest_expiry`、`near_expiry`。

**Makefile 汇总**：
```make
quick:
	python -m pytest -q \
	  tests/quick/test_inbound_pg.py::test_inbound_receive_and_putaway_integrity \
	  tests/quick/test_putaway_pg.py::test_putaway_integrity \
	  tests/quick/test_outbound_pg.py \
	  tests/quick/test_outbound_http_pg.py \
	  tests/quick/test_snapshot_inventory_pg.py \
	  -s --maxfail=1
```
> CI 里直接跑 `make quick` 即可；Docker 口径可将 `PYTEST_CMD` 切换为 `docker compose exec app ... pytest`。

---

## 5. 排障关键节点（变更记录）
1) **Alembic `KeyError: 'url'`** → `alembic/env.py` 增加从 `DATABASE_URL` 读 URL 并写回 config；或在 `alembic.ini` 增加默认 URL。
2) **psql 连接失败** → `postgresql+psycopg://` 为 SQLAlchemy 前缀；`psql` 需使用 `postgresql://` 或显式 `-h -p -U -d`。  # pragma: allowlist secret
3) **路由 500 且 `jq` 解析失败** → 临时将路由包裹 try/except 返回 JSON；最终回归全局异常处理。
4) **列缺失/约束**：
   - `stock_ledger.location_id` 不存在 → 记账不写此列，使用 `stock_id` 关联。
   - `after_qty NOT NULL` → 记账前计算 `after_qty` 并写入。
   - `occurred_at NOT NULL` → 记账时 `NOW()`。
   - `items.spec` 不存在 / `sku NOT NULL` → 查询不依赖 `spec`；造数插入 `sku`。
5) **事务冲突**：
   - 测试基座已启事务 → 用 `begin_nested()`（保存点）；HTTP 用例为每请求创建新 `AsyncSession`，避免并发冲突。

---

## 6. 命令速查
```bash
# 数据库 URL（本机 5433）
export DATABASE_URL='postgresql+psycopg://wms:wms@127.0.0.1:5433/wms'  # pragma: allowlist secret

# 迁移 & 查看
alembic heads -v
alembic upgrade head

# 起后端
uvicorn app.main:app --reload

# 自检接口
curl -s http://127.0.0.1:8000/snapshot/inventory | jq '.items[0]'

# 出库幂等（先造库存）
psql -h 127.0.0.1 -p 5433 -U wms -d wms -c "INSERT INTO stocks(item_id,location_id,qty) VALUES (1,1,10)
  ON CONFLICT (item_id,location_id) DO UPDATE SET qty=EXCLUDED.qty;"

curl -s -H 'Content-Type: application/json' \
  -d '{"ref":"SO-CLI-1","lines":[{"item_id":1,"location_id":1,"qty":1}]}' \
  http://127.0.0.1:8000/outbound/commit | jq

# quick 针刺
make quick
```

---

## 7. 文件改动索引（最终态）
- **迁移**：`alembic/versions/20251016_add_outbound_commits.py`
- **路由**：
  - `app/api/endpoints/outbound.py`
  - `app/api/endpoints/snapshot.py`（含新 `/snapshot/inventory`）
- **服务**：
  - `app/services/outbound_service.py`
  - `app/services/snapshot_service.py`（含 `query_inventory_snapshot()`；模块级代理函数同名）
- **Schemas**：`app/schemas/outbound.py`
- **测试**：
  - `tests/quick/test_outbound_pg.py`
  - `tests/quick/test_outbound_http_pg.py`
  - `tests/quick/test_snapshot_inventory_pg.py`
- **构建**：`Makefile`（`make quick` 汇总跑）

---

## 8. 下一步建议
- **FEFO 精准到期口径**：`earliest_expiry` 仅统计 `batches.qty>0`；或从“批次现势视图”读取。
- **/snapshot/inventory 支持分页/搜索**：`?q=&offset=&limit=`；前端列表更顺滑。
- **/outbound/commit 整单原子模式开关**：`OUTBOUND_ATOMIC=true` 时，任一行不足即 409 并回滚整单。
- **/stock/query**：供出库表单显示“可用量提示”；后续可引入“预留/分配”口径。

> 至此，Phase 2 的 **真接口对接** 主链完成：前端可切真后端，后端幂等/事务/审计合一，quick/HTTP/并发验证齐备。
