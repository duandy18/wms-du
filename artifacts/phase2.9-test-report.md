# Phase 2.9 测试验证报告（草稿）

**日期**：$(date +%F)
**环境**：Postgres@127.0.0.1:5433 / DB=wms

## 一、范围
- 统一口径：库存维度 (warehouse_id, item_id, batch_code)
- 唯一事实源：stocks.qty（保留 snapshots.qty_on_hand 作为目标字段）
- 服务口径：StockService.adjust (INBOUND/OUTBOUND/COUNT)，FEFO 仅提示不强制
- 出库服务：OutboundService v2（逐行委托 adjust）

## 二、结果汇总
- Unit：14/14 ✅（见 artifacts/junit-unit.xml）
- Quick（v2 核心）：4 ✅ / 30 ⏸（见 artifacts/junit-quick-v2.xml）
  - 通过：inbound→pick→count v2；outbound commit v2；outbound core v2（如有）；……
  - 暂挂：依赖 legacy location / HTTP / 平台事件 / 旧视图 的用例，待 Phase 3 适配

## 三、关键断言
- 幂等：以 (reason, ref, ref_line, item_id, batch_code, warehouse_id) 命中唯一键，重复提报零副作用
- 三一致抽查：stocks.qty == SUM(ledger.delta)；snapshots.qty_on_hand 对齐 stocks 聚合
- FEFO：仅排序+提示，不阻断实际扣减

## 四、变更清单（摘录）
- Alembic:
  - add stocks.qty（int）并回填；安装 qty↔qty_on_hand 同步触发器（过渡期）
- 代码：
  - 全面切读 stocks.qty；保留 snapshots.qty_on_hand 目标字段
  - MovementType 新增 OUTBOUND 别名映射 SHIPMENT
  - OutboundService v2：逐行调用 StockService.adjust

## 五、遗留与计划
- Phase 3：
  - 适配 scan handlers(receive/pick/count) 到 adjust
  - 回收 HTTP/订单/平台事件类 quick/grp_flow
  - 迁移收尾：移除触发器、删除 stocks.qty_on_hand、瘦身重复唯一键
