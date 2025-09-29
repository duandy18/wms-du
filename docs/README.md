# WMS-DU 文档总览

这里是 WMS-DU 项目的文档入口，覆盖开发约定、架构设计、业务模块说明等内容。  
目标是：让新成员 10 分钟内熟悉项目背景，老成员随时能快速查阅规范与设计。

---

## 1. 开发与协作
- [CONVENTIONS.md](../CONVENTIONS.md) — 项目开发约定（语言、符号、命名、提交信息、测试）
- [DEV-CHEATSHEET.md](DEV-CHEATSHEET.md) — 开发环境与常用命令速查（本地、CI、Alembic、Tailscale 等）

---

## 2. 系统设计
- `ARCHITECTURE.md` — 系统总体架构（应用分层、依赖关系、服务边界）
- `SECURITY.md` — 用户、角色、权限设计（RBAC 模型与鉴权依赖）
- `DATABASE.md` — 数据库规范与表结构说明
- `API-GUIDE.md` — REST API 路径、状态码约定与示例

---

## 3. 业务模块
- `050_PURCHASE.md` — 采购管理模块（供应商、采购单、收货流程）
- `060_INBOUND.md` — 入库流程
- `070_OUTBOUND.md` — 出库流程
- `080_INVENTORY.md` — 库存台账与批次管理
- `090_RECONCILE.md` — 对账与报表
- `170_PDD_INTEGRATION.md` — 拼多多对接方案（接口映射、限流、错误处理）

---

## 4. 运维与部署
- `DEPLOY.md` — 部署说明（环境变量、Docker、CI/CD）
- `MONITORING.md` — 系统监控与告警方案
- `OPS-GUIDE.md` — 日常运维手册（日志、备份、恢复）

---

## 5. 附录
- `GLOSSARY.md` — 项目术语表（SKU、PO、Receipt 等）
- `CHANGELOG.md` — 版本更新记录
- `ROADMAP.md` — 实施路线图与里程碑追踪

---

## 使用约定
- 文档文件名统一大写+下划线（如 `SECURITY.md`、`API-GUIDE.md`）。  
- 内容按模块拆分，保持简短、直观，不要在单个文件里堆过多信息。  
- 与代码紧密相关的说明（如数据模型、API 参数）应和对应模块的代码变更同步更新。  

---

> 本文档入口版本：v0.1（2025-09）  
> 负责维护人：开发团队全体  
> 更新频率：与每次业务模块迭代同步
