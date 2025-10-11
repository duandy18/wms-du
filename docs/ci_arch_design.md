🧱 CI 架构设计说明

duandy18 / wms-du
Version 1.0 · 2025-10-12

一、设计目标

为 WMS-DU 项目建立一套统一、可复现、跨环境一致的持续集成体系。
重点在于平衡三件事：

稳定性 —— 确保每次合并前代码质量恒定；

透明性 —— CI 逻辑完全可在本地复现；

低维护成本 —— 尽可能减少分散的配置文件和依赖。

二、核心理念
核心点	说明
单一入口	所有 CI 执行逻辑都集中在 .github/ci/run.sh，避免 YAML 膨胀。
单一检查	只保留一个 Job（Full (PG + pytest only)）做为主干保护项。
单一依赖源	彻底弃用 requirements.txt，所有依赖集中在 pyproject.toml。
本地=云端	无论是 CI 还是家用电脑，本地运行结果完全一致。
三、CI 文件结构
.github/
 ├── workflows/
 │   └── ci.yml              # 统一 CI 入口（单 job 模式）
 └── ci/
     └── run.sh              # 实际执行逻辑
app/
 └── sitecustomize.py        # SQLite 补丁：去除 server_settings
docs/
 ├── ci_protection_setup.md  # 分支保护配置说明
 └── ci_arch_design.md       # CI 架构设计说明（本文件）
bootstrap_home.sh            # 本地一键环境初始化脚本
pyproject.toml               # 唯一依赖声明

四、设计特点与优势
1️⃣ 单 Job · 单检查 · 单规则

工作流名：App CI - Bootstrap

Job 名：Full (PG + pytest only)

分支保护绑定这一项。

优势：

主干可合并条件唯一，逻辑清晰。

不存在多 job 相互等待或状态竞争。

CI 报告集中、直观。

2️⃣ 统一依赖管理（Pyproject-only）
[project]
dependencies = [
  "fastapi>=0.110",
  "uvicorn>=0.29",
  "pydantic-settings>=2.2",
  "APScheduler>=3.10",
  "aiosqlite>=0.20",
]


CI 安装命令：

pip install -e ".[pg,dev]"


优势：

无多余文件；

安装命令统一（本地与 CI 一致）；

更符合 PEP-621 标准；

extras（[pg,dev]）清晰区分运行期与开发期依赖。

3️⃣ SQLite / PostgreSQL 双模式兼容
环境	默认数据库	机制
本地	SQLite	sitecustomize.py 自动剥离无效参数
CI	PostgreSQL	Docker 服务 postgres:14-alpine

创新点：

用猴补丁消除 SQLite 与 PostgreSQL 的方言差异；

用 INSERT OR IGNORE + UPDATE 代替 ON CONFLICT 实现兼容 UPSERT；

本地无需数据库服务，测试仍可完全运行。

优势：

跨后端可测；

无需额外配置数据库；

单元测试在任何设备上都能运行。

4️⃣ run.sh 驱动的执行模型

CI、开发者、家机都运行同一个脚本：

bash .github/ci/run.sh


优点：

YAML 中不再混杂命令逻辑；

本地可直接复现 CI；

测试流程一致性 100%。

5️⃣ 本地友好：sitecustomize + bootstrap_home.sh
文件	功能
sitecustomize.py	自动修复 SQLite 参数问题
bootstrap_home.sh	本地一键初始化环境、安装依赖、运行最小测试

执行：

bash bootstrap_home.sh


输出：

✅ Bootstrap done.
Activate:  source .venv/bin/activate
Guard on:  export WMS_SQLITE_GUARD=1

五、优劣势对比
项目	旧式方案	现行方案	优势总结
Workflow 结构	多 job、多文件	单 job 单 workflow	更清晰、更快
依赖声明	requirements.txt	pyproject.toml	无重复、版本一致
测试数据库	仅 PostgreSQL	SQLite + PG 双通	本地可测
执行逻辑	硬编码在 YAML	独立 run.sh	可本地复现
分支保护	多检查	单一检查	逻辑唯一、合并明确
六、未来扩展
改进方向	说明
拆分 lint 与 typecheck job	让 Ruff、Mypy 结果单独展示
提升覆盖率门槛	从 45% → 60%
增加缓存	用 actions/cache 加快安装速度
引入 bumpver / Hatchling	自动化版本号管理
发布分支保护	针对 release/vX.Y.Z 分支独立规则
七、总结

我们将传统多层 CI/CD 体系，收敛成一个本地可复现、跨数据库可测试、
单文件驱动、零外部依赖、极简而稳定的架构。

它是 “够用、稳健、低维护” 的理想形态：

💡 开发者思考逻辑而非工具，CI 成为验证的伙伴而非障碍。

八、文档索引
文档	内容
docs/ci_protection_setup.md	分支保护与 GitHub 设置步骤
docs/ci_arch_design.md	本文件：CI 架构理念与技术设计
bootstrap_home.sh	本地一键初始化脚本
.github/ci/run.sh	CI 统一执行逻辑
.github/workflows/ci.yml	Workflow 配置入口

✅ 现状总结
CI 状态：全绿
分支保护：生效
依赖声明：统一
环境：可复现
主干：线性、可追踪、受保护
