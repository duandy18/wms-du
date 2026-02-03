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
  被下面所有现役业务调用：

  - InboundService（入库）
  - PickService（扫码拣货）
  - OutboundService（出库扣减）
  - ReservationConsumer（软预占消费，历史能力，已收敛）
  - EventProcessor（已 deprecated，历史调用）

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
  - （v2 架构下）不再承担 location 逻辑，使用 batch 作为主粒度

- `scan_handlers/receive_handler.py`
  Scan v2 的收货 handler：

  - 经由 `scan_orchestrator` 调用
  - 构造 ref / trace_id
  - 最终进入 `InboundService + StockService.adjust`

---

### 2.3 预占链路（已移除）

- `reservation_service.py`
  Soft Reserve 头表/明细 + 状态机（历史）：

  - `persist()`：幂等建/改 reservation + reservation_lines
  - `get_by_key() / get_lines()`：以业务键找单 & 行
  - `mark_consumed() / mark_released()`：状态迁移
  - 引入 `trace_id`，与订单 / 出库 / trace 对齐

  当前状态说明：

  - 原 soft reserve HTTP 接口（`/reserve/*`）已移除
  - 当前系统不再提供任何预占类 API
  - **出库唯一裁决点为 Pick Task Commit（见 2.4）**

> ✅ 旧的 lock-based Reserve（`_deprecated legacy reservation modules` 等）已经放入 `_deprecated`。
> Soft Reserve v2 是**最后一代预占实现**，现阶段仅作为历史参考存在。

---

### 2.4 出库链路（Pick → Outbound → Ship）

- `pick_service.py`
  v2 拣货服务：

  - 输入：`item_id, warehouse_id, batch_code, qty, ref`
  - 检查后调用 `StockService.adjust(delta=-qty, reason=PICK)`
  - 返回扣减后的库存结果
  - 对应前端 `ScanPickPage` 和 Outbound 拣货页面

- `pick_task_commit_ship.py`
  Pick Task Commit（**唯一库存裁决点**）：

  - 聚合 Scan 阶段采集的事实
  - 并发安全（幂等证据 + advisory lock）
  - 真相回读 `outbound_commits_v2`
  - 返回稳定的 `trace_id / committed_at / diff`

- `outbound_service.py`
  Phase 3 出库引擎（Ship v3）：

  - 聚合同一 `(item_id, warehouse_id, batch_code)` 的扣减请求
  - 用 `order_id` 作为 ref，基于 `stock_ledger` 查“已扣数量”，只扣“剩余需要扣”的部分（幂等）
  - 调用 `StockService.adjust` 写负向 `OUTBOUND_SHIP` 台账

- `ship_service.py`
  发运审计服务：

  - 不扣库存，只写 `audit_events(flow=OUTBOUND, event=SHIP_COMMIT)`
  - 幂等：同 ref 多次提交只记一次
  - 用于 `/outbound/ship/commit` 路由里的发运记录

---

### 2.5 平台事件链路（Platform → Pick / Ship）

- `platform_adapter.py`
  各平台事件解析适配器：

  - `PlatformAdapter` 抽象类
  - `PDDAdapter / TaobaoAdapter / TmallAdapter / JDAdapter / DouyinAdapter / XHSAdapter`
  - 把平台原始 payload 标准化为：
    `{platform, order_id, status, lines, shop_id, raw, ship_lines}`

- `platform_events.py`
  平台事件主编排：

  - 根据 platform + status 分类为：`PICK / CANCEL / SHIP / IGNORE`
  - **PICK**：
    `OrderService.enter_pickable` → 生成拣货任务 / 打印队列（不做预占）
  - **CANCEL**：
    `OrderService.cancel` → 取消订单执行态
  - **SHIP**：
    直接走 `PickTaskCommitShip` 硬出库（库存裁决点）
  - 全程写入 `EventWriter(source="platform-events")` 进行审计

> 这是你未来 “平台订单 → 仓库拣货 → 出库” 的唯一主线，不再通过杂乱的库存搬运能力实现。

---

### 2.6 订单 & 路由

- `order_service.py`

  - 创建订单时生成 `trace_id = new_trace("http:/orders")`
  - 负责订单状态与 Pick / Outbound 的 glue

- `warehouse_router.py`

  - 决定多仓模式下订单应该落到哪个仓
  - 多仓逻辑以 `warehouse_id` 为第一原则

---

### 2.7 主数据 & 权限

- `store_service.py`
  店铺（platform, shop_id）定义与仓库绑定。

- `item_service.py`
  商品主数据。

- `user_service.py / role_service.py / permission_service.py`
  用户 & 权限体系。
