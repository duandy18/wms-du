# WMS-DU 测试规范（Phase 2.1）

## 0. 总原则
- 只改 tests，不动主程序与迁移链。
- 造数必须批次粒度：batches → stocks。
- 外层控事务；读后 commit；业务 begin。
- 避免 asyncpg 类型歧义：locations(code,name) 不复用同一个绑定。
- 契约断言以新口径为准（Inbound 返回 on_hand_after 等）。

## 1. 批次粒度造数
详见 `tests/helpers/inventory.py::seed_batch_slot/seed_many`。

## 2. 事务边界
- 造数结束：`await session.commit()`
- 读取后若要 `begin()`：先 `await session.commit()`
- 业务动作：`async with session.begin(): ...`

## 3. 常见服务用法
- 入库：`InboundService.receive(..., batch_code, expiry_date, occurred_at)`
- 出库：`OutboundService.commit(..., lines=[OutboundLine], occurred_at, mode='FEFO'|'NORMAL', allow_expired)`
- 移库：`PutawayService.putaway(..., left_ref_line=奇数，两腿+1)`
- 对账：`ReconcileService.reconcile(actual_qty=...)`
- FEFO 分拨：`FefoAllocator.plan(..., occurred_date?)` / `FefoAllocator.ship(..., occurred_at)`

## 4. 快照
表结构：`as_of_ts / snapshot_date / qty_on_hand / qty_available / qty_allocated / qty`
插入与日聚合范式见 `tests/helpers/inventory.py::insert_snapshot`。

## 5. 幂等/并发
- 幂等键：`(reason, ref, ref_line, stock_id)`；重放不再扣减。
- tests 中已通过 conftest 的 shim 做 EXISTS + INSERT ... WHERE NOT EXISTS + FOR UPDATE 加锁，测试仅需按契约传参。

## 6. 易错 CheckList
- [ ] locations(code,name) 用不同绑定或 CAST
- [ ] 读后 commit 再 begin
- [ ] Inbound 断言 on_hand_after
- [ ] 快照插入补齐 NOT NULL
- [ ] 幂等第二次 total_lines==0、库存不变
- [ ] Reconcile 用 actual_qty
