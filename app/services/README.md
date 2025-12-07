# WMS-DU 后端服务层蓝图（app/services）

> 目标：把“真正还在用的服务”和“阶段性/历史产物”分清楚，
> 让以后所有功能变更都围绕一条干净的主线，而不是在一堆历史文件里迷路。

---

## 1. 总体分层

服务层按三类划分：

- **A 类：主干服务（Active）**
  当前架构的唯一真相，所有新功能必须围绕它们扩展。

- **B 类：阶段性服务（Staged）**
  仍有参考价值，但不应被现役业务直接调用；作为未来重构素材。

- **C 类：废弃服务（Deprecated）**
  仅为历史追溯/测试存在，不再参与现役调用链。

---

## 2. 主干服务（A 类）一览

### 2.1 库存核心：Stock & Snapshot

- `stock_service.py`
  唯一库存调整引擎：**所有增减库存必须走 `StockService.adjust`**。
  被下面所有业务调用：

  - InboundService（入库）
  - PickService（扫码拣货）
  - OutboundService（出库扣减）
  - ReservationConsumer（软预占消费）
  - InventoryOpsService（仓内搬运）
  - EventProcessor（已 deprecated）过去也用过

- `snapshot_service.py`
  快照 & 对账服务：从 `stocks + ledger` 刷新快照表，并夹带一致性检查逻辑。
  对应前端 `SnapshotPage`。

- `stock_fallbacks.py`
  FEFO 分配器（猫粮业务定制），只负责“如何从 stocks 选出批次计划”，
  真正扣减仍在 `StockService.adjust` 里执行。

---

### 2.2 入库链路（Inbound）

- `inbound_service.py`
  负责入库（收货）：
  - 按 `(warehouse_id, item_id, batch_code)` 粒度写 stocks / ledger
  - （v2 架构下）不再承担 location 逻辑，使用 batch 作为主粒度。

- `scan_handlers/receive_handler.py`
  Scan v2 的收货 handler：
  - 经由 `scan_orchestrator` 调用，构造 ref/trace_id，最终进入 `InboundService + StockService.adjust`。

---

### 2.3 预占链路（Soft Reserve v2）

- `reservation_service.py`
  Soft Reserve 头表/明细 + 状态机：
  - `persist()`：幂等建/改 reservation + reservation_lines
  - `get_by_key() / get_lines()`：以业务键找单 & 行
  - `mark_consumed() / mark_released()`：状态迁移
  - 引入 `trace_id`，与订单/出库/trace 对齐。

- `reservation_consumer.py`
  Soft Reserve 消费器：

  - `pick_consume()`：
    - 读取 reservation_lines
    - 通过 `StockService.adjust(delta<0)` 扣库存
    - 更新 `reservation_lines.consumed_qty` + 头表状态
  - `release_expired_by_id()`：TTL 回收，将 `status=open` 的单标记为 `expired`（不动库存）。

- `soft_reserve_service.py`
  对外 façade：
  - `/reserve/persist`
  - `/reserve/pick/commit`
  - `/reserve/release`
  入口在 `app/api/routers/reserve_soft.py` 中。

> ✅ 旧的 lock-based Reserve（`reservation_lock / reservation_release / reservation_alloc / reservation_plan` 等）已经放入 `_deprecated`，
> Soft Reserve v2 是**唯一现役预占引擎**。

---

### 2.4 出库链路（Pick → Outbound → Ship）

- `pick_service.py`
  v2 拣货服务：

  - 输入：`item_id, warehouse_id, batch_code, qty, ref`
  - 检查后调用 `StockService.adjust(delta=-qty, reason=PICK)`
  - 返回扣减后的库存结果
  - 对应前端 `ScanPickPage` 和 Outbound 拣货页面。

- `outbound_service.py`
  Phase 3 出库引擎（Ship v3）：

  - 聚合同一 `(item_id, warehouse_id, batch_code)` 的扣减请求
  - 用 `order_id` 作为 ref，基于 `stock_ledger` 查“已扣数量”，只扣“剩余需要扣”的部分（幂等）
  - 调用 `StockService.adjust` 写负向 `OUTBOUND_SHIP` 台账
  - 出库成功后调用 `_consume_reservations_for_trace()`，根据 trace_id 自动消费 open reservation_lines（打通预占→出库闭环）

- `ship_service.py`
  发运审计服务：

  - 不扣库存，只写 `audit_events(flow=OUTBOUND, event=SHIP_COMMIT)`
  - 幂等：同 ref 多次提交只记一次
  - 用于 `/outbound/ship/commit` 路由里的发运记录。

---

### 2.5 平台事件链路（Platform → Reserve/Cancel/Ship）

- `platform_adapter.py`
  各平台事件解析适配器：

  - `PlatformAdapter` 抽象类
  - `PDDAdapter / TaobaoAdapter / TmallAdapter / JDAdapter / DouyinAdapter / XHSAdapter`
  - 把平台原始 payload 标准化为：
    `{platform, order_id, status, lines, shop_id, raw, ship_lines}`

- `platform_events.py`
  平台事件主编排：

  - 根据 platform + status 分类为：`RESERVE / CANCEL / SHIP / IGNORE`
  - **RESERVE**：
    `OrderService.reserve` → Soft Reserve persist
  - **CANCEL**：
    `OrderService.cancel` → Soft Reserve release
  - **SHIP**：
    先 `SoftReserveService.pick_consume`（有 reservation 就吃掉）
    若无 reservation，则走 `OutboundService.commit` 硬出库
  - 全程写入 `EventWriter(source="platform-events")` 进行审计。

> 这是你未来 “平台订单 → 仓库预占 → 出库” 的唯一入口，不再通过杂乱的事件总线实现。

---

### 2.6 订单 & 路由

- `order_service.py`
  - 创建订单时生成 `trace_id = new_trace("http:/orders")`，写入 orders.trace_id
  - 负责订单状态与 Reserve/Outbound 的 glue。

- `warehouse_router.py`
  - 决定多仓模式下订单应该落到哪个仓（现在多仓逻辑还比较轻，但骨架已在）。

- `order_adapters/base.py` + `order_adapters/pdd.py`
  - CanonicalOrder + PDD 订单适配器（已移入 `_staged/platform/order`，等待未来平台订单入口重构）。

---

### 2.7 仓内搬运（InventoryOps）

- `inventory_ops.py`（InventoryOpsService）

  - 用于“同仓库内 A 库位 → B 库位搬运”：
    - 调用两次 `StockService.adjust`：
      - from_location：delta = -qty（reason=PUTAWAY）
      - to_location  ：delta = +qty（reason=PUTAWAY）
  - 被 `stock_transfer` / `inventory` 路由使用。

> 这部分仍然基于 `location_id`，属于 **现役但未来会改造** 的服务（配合你取消 location 业务后的 v3）。

---

### 2.8 诊断与审计

- `trace_service.py`
  - 聚合 `event_store + audit_events + stock_ledger + reservations + outbound`
  - 对应前端 Trace 链路页面 / DevConsole 的 Scan panel。

- `audit_writer.py / audit_logger.py`
  - 统一写入 `event_log` / `event_store`，并自动带上 trace_id、source 等。

---

### 2.9 主数据 & 权限

- `store_service.py`
  - 店铺 (platform, shop_id) 定义与仓库绑定
  - 多仓路由与 ChannelInventory 依赖它。

- `item_service.py`
  - 商品主数据。

- `user_service.py / role_service.py / permission_service.py`
  - 用户 & 权限体系。

---

## 3. 阶段性服务（B 类，_staged）

这些服务当前不直接参与主干调用，但有结构价值，未来某个 Phase 可能会重构整合进去。

建议组织结构：

```text
app/services/_staged/
  reservation/
    reservation_persist.py
    reservation_plan.py
    reservation_alloc.py
  outbound/
    outbound_v2_service.py
  inventory/
    inventory_adjust.py (旧大引擎)
    inventory_ops_v1.py (若有)
  platform/
    order_adapters/
      base.py
      pdd.py
    # 未来：其它平台订单适配器
