# 库存快照（StockSnapshot）设计与实现

## 1. 目标
- 固化每日库存余额，支持历史查询与趋势分析；
- 幂等：同一日重复生成不会重复写入；
- 可回补历史；
- 可扩展成本维度（Moving Average / FIFO）。

## 2. 粒度（Grain）
`snapshot_date, warehouse_id, location_id, item_id, batch_id`
> 说明：`warehouse_id` 来自 `locations` 关联或 `batches.warehouse_id`:contentReference[oaicite:2]{index=2}:contentReference[oaicite:3]{index=3}。

## 3. 字段
- `qty_on_hand`: 当日账面库存
- `qty_allocated`: 当日已分配（占用）
- `qty_available = qty_on_hand - qty_allocated`
- `expiry_date`, `age_days`
- 索引：`(snapshot_date)`, `(item_id, snapshot_date)`, `(warehouse_id, snapshot_date)`, `(expiry_date, snapshot_date)`
- 唯一约束：`(snapshot_date, warehouse_id, location_id, item_id, batch_id)`

## 4. 数据来源
- **权威**：`batches`（真实批次 + `UNBATCHED` 虚拟批次）
- 可选补齐：将 `stocks` 的“无批次余额”同步到 `batches.UNBATCHED`
  - 公式：`UNBATCHED = max(stocks_sum - real_batches_sum, 0)`

## 5. 生成机制
- 每日 00:05 生成昨日快照（APScheduler）；
- 手动：`POST /snapshot/run?date=YYYY-MM-DD`
- 回补：`POST /snapshot/run-range?from=YYYY-MM-DD&to=YYYY-MM-DD`

## 6. 幂等策略
- 依赖唯一键 + SQLite/PG 原生 UPSERT：
  - `ON CONFLICT (snapshot_date, warehouse_id, location_id, item_id, batch_id) DO UPDATE`

## 7. 趋势与分析
- 走势：按 `(item_id, snapshot_date)` 聚合
- 库龄：根据 `age_days` 分桶（0–30 / 31–60 / 61–90 / 90+）
- 到期预警：`expiry_date` with `snapshot_date` 过滤

## 8. 成本维度（v2.1 预告）
- 新增列：`unit_cost`, `inventory_cost`, `valuation_method`
- 计算：先用移动加权（Moving Average），截止到 `snapshot_date` 为止
- 不改唯一键，仅增列与计算过程

## 9. 性能建议
- 仅存非零行（可选开关）
- 大仓分仓并行 / 分区（PG）
- 定期归档老快照

## 10. 常见问题
- SQLite 迁移：唯一约束需在 `CREATE TABLE` 内声明（避免 ALTER 失败）:contentReference[oaicite:4]{index=4}
- `stocks` 无 `warehouse_id`：通过 `locations` JOIN 或用 `batches` 的 `warehouse_id`
