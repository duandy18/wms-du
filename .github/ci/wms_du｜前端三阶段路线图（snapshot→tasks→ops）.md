# WMS-DU｜前端三阶段路线图（Snapshot → Tasks → Ops）

> 目标：以“首页库存快照 + 三大任务页（Inbound / Putaway / Outbound）+ 查询审计（Stock / Ledger）”为主线，先前端自给自足（MSW），再与 FastAPI 联调，最后补运维与可观测性。

---

## 阶段一（MVP）：能看、能做、能查（闭环）
**时间建议：1–2 天**

### A. 页面与路由
- `/` **Snapshot（库存快照）** — *可选：阶段一可暂用简卡，阶段二强化*
- `/inbound` 收货（Inbound）
- `/putaway` 上架（Putaway）
- `/outbound` 出库（Outbound）
- `/stock` 现势查询（工具）
- `/ledger` 台账（工具）

### B. 职责边界（不打架）
- **Inbound**：把货“纳入系统”（总量 **↑**），默认落 **STAGE**。
- **Putaway**：在仓内移动（总量 **＝**），`from(STAGE) → to(目标位)`。
- **Outbound**：把货“移出系统”（总量 **↓**）。

### C. 接口契约（前端 zod ⇄ 后端 Pydantic）
- `POST /inbound/receive` → `{ item_id, accepted_qty, batch_code? }`
- `POST /putaway` → `{ item_id, location_code, qty, batch_code?, from_location_code? }`
- `POST /outbound/commit` → `{ item_id, location_code, qty, ref, batch_code? }`
- `GET /stock/query` → `{ rows:[{ item_id, location_code, qty, batch_code? }] }`
- `GET /ledger/recent?limit` → `{ rows:[{ id, ts, item_id, location_code, delta, reason, ref?, batch_code? }] }`

> 错误统一：`{ detail: string, code?: string }`；前端 toast 直出 `detail`。

### D. MSW（离线先飞）
- handlers：`/inbound/receive`、`/putaway`、`/outbound/commit`、`/stock/query`、`/ledger/recent`。
- 开关：`.env.local` → `VITE_USE_MSW=1` 开启，删掉即连真后端。

### E. 组件基座
- **AppShell**（顶栏导航 + 容器）
- **FormKit**（Label/Input/Error/Help 组合）
- **DataTable**（最简表格 + 空态 + 导出 CSV）
- **Toaster**（已具备）
- **ApiBadge**（右上显示 `VITE_API_URL` 与 `MSW` 状态）

### F. DoD（验收）
- 三大任务页：表单 **Loading/Success/Error** 可见；zod 先校验。
- 工具页：能查、能导出；Ledger 显示 `Σdelta`。
- 守恒：`Σ(stocks.qty)` 与 Ledger 累计相符（肉眼核对近 20 条）。

---

## 阶段二（任务驱动）：前置/后置与可视化
**时间建议：2–3 天**

### A. 新增页面
- `/tasks/inbound` 待收货清单（**前置**）：`task_id, po_no, supplier, item, expect_qty, eta` → 跳 `/inbound?...`
- `/batches` 批次面板（**侧向**）：近 30 天批次、FEFO 排序、到期标记、库位分布。
- `/moves` 移动记录（**后置回放**）：24h Putaway/Transfer 展平展示；由 `/ledger/recent` 归并 -x/+x。

### B. 首页 Snapshot 强化
- **KPI 卡**：`total_qty / stage_qty / inbound_24h / outbound_24h / near_expire_count`
- **TopN 清单**：待收货 / 待上架（from STAGE）
- **位置热力**：按区域（RACK-A/B/C、STAGE、PICK）聚合
- **视图切换**：表格视图 ↔ 图块视图（Tile UI，适配触屏），抽屉显示“库位/批次”细分

### C. 接口增强（可先 MSW）
- `GET /snapshot/kpis`、`/snapshot/todo-inbound`、`/snapshot/todo-putaway`、`/snapshot/location-heat`
- `GET /batches/recent?item_id&days=30`
- `GET /tasks/inbound`、`POST /tasks/inbound/ack|done`

### D. 守恒自检条（页面底部）
- 显示 24h `Σdelta` 与 `/stock/query` 的差值（应为 0），异常高亮。

### E. DoD
- 三页（tasks/batches/moves）可用：Loading/Empty/Error 明确；点击跳转携参。
- 首页：图块与表格切换无抖动，抽屉能看分布与 FEFO 时间线。
- 守恒自检为 0；异常时可定位到 Ledger 具体记录。

---

## 阶段三（运维与可靠性）：鉴权、健康、设置
**时间建议：1–2 天**

### A. 新增页面
- `/system/health` 系统健康：`{ app_version, db_rev, sum_stocks, sum_ledger_delta }`、DB 连接、迁移状态。
- `/settings` 设置：API 源切换、MSW 开关（持久化 localStorage）、主题偏好。
- `/admin/refs` 参照维护（后置）：Items/Locations 批量导入与修正（CSV 上传 + 预览）。

### B. 鉴权（最小可行）
- 登录态本地存储 Token；Axios 拦截器加 `Authorization`。
- 后端 CORS: `allow_credentials=True`；Cookie 场景配 `SameSite=None; Secure`。

### C. 可观测性
- 全局 ErrorBoundary（上报到日志端点或 Sentry 预留）。
- API 调用耗时与失败率简单统计（控制台或简报表）。

### D. DoD
- Health 页面绿色通过；Settings 切换源即时生效；常见错误有可读 `detail`。

---

## 附：信息架构与字段口径（首页 + 任务页）

### 1) 首页（Snapshot）展示字段
- `item_id`、`item_name`、`spec`（1.5kg/袋）
- `qty_total`（总数）
- `locations`（Top2 拼接：“RACK-A1×60, RACK-B2×40；STAGE×0”）
- `batches`（主批次 + 最早到期：“B20251015（2026-10-01）”）
- `near_expire / expired`（临期≤30天 / 已过期）

### 2) 三大任务页共性
- 表单：zod 强校验 → 统一 API 层 → toast 提示。
- 即时参照：提交前显示来源位/目标位可用量（`/stock/query`）。
- 幂等：Inbound/Outbound 使用 `ref`（或 `ref+line`）。

---

## 里程碑（建议节拍）
- **M1（Day 1）**：Putaway 首联调跑通；Stock/Ledger 可查询；MSW 开关工作。
- **M2（Day 2–3）**：任务三页稳定；首页 Snapshot 上线（图块/表格 + 抽屉）；守恒自检条。
- **M3（Day 4）**：Health/Settings 上线；Outbound 与真实后端联通；提交阶段总结。

---

## 风险与对策
- **字段漂移**：以 `contracts.ts` 为单一事实源，`api.ts` 入参出参 `*.parse()`。
- **CORS/跨域**：FastAPI 中开启 `localhost/127.0.0.1:5173`；必要时 Vite 代理 `/api`。
- **批次/库位约束差异**：在阶段一先放松，阶段二由后端返回明确错误码并在前端做友好提示。
- **性能**：首页列表分页与虚拟滚动；接口加简单缓存（30s）。
