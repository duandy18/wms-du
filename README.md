# WMS-DU

WMS-DU backend service for WMS / OMS / TMS / PMS.

当前后端目录清理原则：

- ORM 模型归属业务模块目录，app/models 全局模型目录已退役。
- 运行代码按业务域收敛，避免全局 services / repos / contracts / helpers / utils 残留。
- 无真实引用的旧脚本、旧 datafix、旧 backfill、旧 demo、旧 smoke 优先删除。
- 删不掉但有真实业务归属的文件，应迁入对应业务模块。
- 不保留 alias / 双轨 / 兼容壳。
- 前后端继续坚持刚性契约。

后端常用入口：

- make alembic-check
- make test TESTS="tests/api/test_no_duplicate_routes.py tests/api/test_user_api.py"
- make lint-backend
- make openapi-export

当前保留的 scripts/ 主要是 Makefile / CI / 测试 / 审计真实入口，不再维护历史一次性修补脚本。

---

## Frontend (wms-web)

本仓库包含前端子工程（Vite + React + MSW）：
- 开发启动：`pnpm dev`
- Mock：MSW（`public/mockServiceWorker.js`），开发环境置 `VITE_USE_MSW=1`
- 入口：`/src/router.tsx`，首页“库存快照 + 三大任务页（Inbound/Putaway/Outbound）+ 工具（Stock/Ledger）”
