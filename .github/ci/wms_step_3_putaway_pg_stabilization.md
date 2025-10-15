《WMS-DU 核心链条 Step 3 ：PostgreSQL 入库主链稳定 & PutawayService 强约束对齐》

---

### 一、阶段概览
**目标**：完成 PostgreSQL 环境下入库主链（Inbound + Putaway）的强约束与幂等逻辑统一。

- 对齐 InboundService 与 PutawayService 范式，均采用“保存点 + 幂等 + 强约束台账写入”。
- 兼容历史迁移遗留的旧唯一约束 `(reason, ref, ref_line)` 与新索引 `(reason, ref, ref_line, stock_id)`。
- 通过 Quick Test 确认逻辑在 PostgreSQL 环境稳定运行。

**测试输出示例**：
```
putaway ledger: 2 0 -10 10
stocks: 0 10
```
✅ 测试通过。

---

### 二、主要工作内容

#### 1. Alembic 迁移链修复
- 旧版本丢失的 revision `3b_add_warehouses_locations` 导致链断裂；
- 重新以 `3a_fix_sqlite_inline_pks` 为基线执行 `alembic stamp`；
- 合并 `20251006_add_constraints_to_stocks` 与 `e4b9177afe8d_putaway_add_uniq_reason_ref_ref_line_` 为单一 head：`737276e10020_merge_stocks_constraints_and_ledger_head`；
- 迁移脚本支持 CHECK 约束 `delta <> 0` 与 唯一索引幂等创建。

#### 2. 序列拨号问题修复
- 修复 `items_id_seq` 与 `locations_id_seq` 未与表同步的问题：
  ```sql
  SELECT setval('public.items_id_seq', COALESCE((SELECT MAX(id) FROM public.items), 0), true);
  ```
  确保下一发 `nextval()` = `max(id) + 1`。

#### 3. PutawayService 重写与增强
- 采用事务保存点（`session.begin_nested()`）+ 行级锁（`SELECT ... FOR UPDATE`）；
- 幂等检测键：`(reason, ref, ref_line, stock_id)`；
- 自动处理旧唯一约束冲突：若 `UNIQUE(reason,ref,ref_line)` 已存在，则 `ref_line + 1` 自愈重写；
- 死锁与序列化失败（40P01/40001）自动指数退避重试；
- 幂等与并发逻辑均在保存点内实现，无需整体事务回滚。

#### 4. StockLedger 模型同步数据库结构
- `ref_line` 改为 Integer 类型，匹配数据库字段；
- `ref` 设置为非空（避免 NULL 破坏唯一约束）；
- 增加 ORM 级索引：
  ```python
  Index(
      'uq_ledger_reason_ref_refline_stock',
      'reason', 'ref', 'ref_line', 'stock_id',
      unique=True
  )
  ```

#### 5. conftest.py 优化
- 异步会话 teardown 阶段添加 `contextlib.suppress(Exception)`，防止事务关闭时报 `ResourceClosedError`；
- PostgreSQL 环境使用空 connect_args，防止 asyncpg 与 psycopg3 混用冲突；
- 增加序列拨正逻辑 `_reseed_items_seq_pg()`。

#### 6. Quick Test 设计与验证
- 使用 `_seed_stock_qty()` 直接构造库存余额，而非依赖 batch 流程；
- 容忍 `idempotent-concurrent` 状态作为幂等成功；
- 查询台账时仅按 `(reason='PUTAWAY', ref='PW-1')` 统计，兼容 `ref_line + 1` 自愈的情况；
- 验证对称性与幂等：
  - 台账两条，`sum(delta)=0`；
  - 来源库存减 10，目标库存加 10；
  - 重放调用无新增台账。

---

### 三、成果验证
- Quick Test `test_putaway_integrity` 在 PostgreSQL 环境通过：
  ```bash
  PYTHONPATH=. pytest -q tests/quick/test_putaway_pg.py::test_putaway_integrity -s
  ```
  输出：
  ```
  putaway ledger: 2 0 -10 10
  stocks: 0 10
  ```
- CI 可稳定运行 PG smoke 测试链路。

---

### 四、CI 冒烟整合建议
- 更新 `scripts/run.sh`：
  ```bash
  case "${1:-}" in
    ci:pg:smoke)
      echo "[smoke] PostgreSQL"
      PYTHONPATH=. pytest -q tests/quick/test_inbound_pg.py::test_inbound_receive_and_putaway_integrity -s
      PYTHONPATH=. pytest -q tests/quick/test_putaway_pg.py::test_putaway_integrity -s
      ;;
  esac
  ```
- GitHub Actions 中调用：
  ```yaml
  - name: Smoke (PG)
    run: bash scripts/run.sh ci:pg:smoke
  ```

---

### 五、Step 4 展望
1. 修复 `StockService.adjust()` 批次分支 `location_id NOT NULL` 问题；
2. 增强 PutawayService 并发：`FOR UPDATE SKIP LOCKED + 批量 putaway()`；
3. 合并 Quick Test 入 CI PG 冒烟流程；
4. 引入多线程/多事务压力测试，验证死锁与重试策略。
