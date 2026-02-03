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
  - 不承担 location 逻辑，以批次作为主粒度

- `scan_handlers/receive_handler.py`
  Scan v2 的收货 handler：

  - 经由 `scan_orchestrator` 调用
  - 构造 ref / trace_id
  - 最终进入 `InboundService + StockService.adjust`

---

### 2.3 出库链路（Pick → Outbound → Ship）

- `pick_service.py`
  v2 拣货服务：

  - 输入：`item_id, warehouse_id, batch_code, qty, ref`
  - 调用 `StockService.adjust(delta=-qty, reason=PICK)`
  - 返回扣减后的库存结果

- `pick_task_commit_ship.py`
  Pick Task Commit（**唯一库存裁决点**）：

  - 聚合 Scan 阶段采集的事实
  - 并发安全（幂等证据 + advisory lock）
  - 真相回读 `outbound_commits_v2`
  - 返回稳定的 `trace_id / committed_at / diff`

- `outbound_service.py`
  出库引擎：

  - 聚合同一 `(item_id, warehouse_id, batch_code)` 的扣减请求
  - 用 ref 作为幂等证据，基于 `stock_ledger` 查“已扣数量”，只扣“剩余需要扣”的部分
  - 调用 `StockService.adjust` 写负向出库台账

- `ship_service.py`
  发运审计服务：

  - 不扣库存，只写 `audit_events(flow=OUTBOUND, event=SHIP_COMMIT)`
  - 幂等：同 ref 多次提交只记一次

---

### 2.4 平台事件链路（Platform → Pick / Ship）

- `platform_adapter.py`
  各平台事件解析适配器：标准化为统一结构。

- `platform_events.py`
  平台事件主编排：

  - PICK：生成仓内执行任务（不触库存裁决）
  - CANCEL：取消订单执行态
  - SHIP：进入硬出库链路（裁决点在 Commit）

---

### 2.5 订单 & 路由

- `order_service.py`
  负责订单状态与 Pick / Outbound glue。

- `warehouse_router.py`
  多仓决策：决定订单应落到哪个仓。

---

### 2.6 主数据 & 权限

- `store_service.py`
  店铺定义与仓库绑定。

- `item_service.py`
  商品主数据。

- `user_service.py / role_service.py / permission_service.py`
  用户与权限体系。
