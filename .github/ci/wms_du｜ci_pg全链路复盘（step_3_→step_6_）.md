# WMS-DU 项目｜CI-PG 全链路复盘（Step 3 → Step 6）

> 本文整合 Step 3、Step 5、CI 转发器、Step 6 四个阶段的 Canvas，形成 WMS-DU 项目的 PostgreSQL 与 CI 全链路基线文档。

---

## 一、总览

### 项目目标
以 **PostgreSQL (PG)** 为核心后端，完成从业务逻辑 → 数据库结构 → 测试验证 → CI 自动化 的全闭环。

### 阶段跨度
- Step 3：Putaway & Inbound 主链稳定；
- Step 5：数据库唯一约束加固与幂等验证；
- CI 转发器阶段：构建稳定 CI 调度体系；
- Step 6：体检扩展与快照链路调试完备。

### 四测四补丁成果图
```
迁移链 ✅ → 体检 ✅ → Quick Tests ✅ → CI ✅
```
- 四测：Inbound 幂等、Putaway 对称、快照幂等、快照回灌；
- 四补丁：约束修复、索引优化、体检增强、快照幂等。

---

## 二、Step 3｜Putaway & Inbound 主链稳定

### 关键成果
- PostgreSQL 环境下主链入库逻辑完全稳定。
- InboundService 与 PutawayService 均采用：
  - **保存点 + 幂等检测 + 强约束台账写入**；
  - 兼容旧唯一约束 `(reason, ref, ref_line)` 与新复合索引 `(reason, ref, ref_line, stock_id)`。

### 关键代码片段
```python
Index(
    'uq_ledger_reason_ref_refline_stock',
    'reason', 'ref', 'ref_line', 'stock_id',
    unique=True
)
```

### 测试结果
```bash
PYTHONPATH=. pytest -q tests/quick/test_putaway_pg.py::test_putaway_integrity -s
putaway ledger: 2 0 -10 10
stocks: 0 10
```
✅ 对称性与幂等验证通过。

---

## 三、Step 5｜数据库唯一约束加固与幂等验证

### 改动摘要
| 文件路径 | 说明 |
|-----------|------|
| `alembic/versions/20251014_uq_ledger_reason_ref_refline.py` | 新增 Ledger 唯一约束。 |
| `alembic/versions/20251014_uq_batches_composite.py` | 新增 Batches 复合唯一约束。 |
| `tests/quick/test_putaway_idempotency_pg.py` | 验证 bulk_putaway 幂等性。 |
| `tools/ensure_pg_ledger_shape.py` | 体检脚本扩展，检测 UNIQUE 约束。 |

### 执行命令
```bash
alembic upgrade head
bash .github/ci/run.sh ci:pg:all
```

### CI 结果
```bash
[ci:pg:migrate] ✅
[ci:pg:verify-ledger] [OK] ledger/stocks shape valid
[ci:pg:quick] ✅ 全部测试通过
[ci:pg:smoke] ✅ HTTP 200 响应
```

✅ 数据库结构防重，幂等性验证完毕。

---

## 四、CI 转发器阶段

### 设计理念
> 策略：**少动 CI，多用 run.sh。**

- CI YAML 仅作外壳，逻辑全部沉入根目录 `run.sh`。
- `.github/ci/run.sh` 为固定入口，永不变动。

### 文件结构
```
.github/
├── ci/
│   ├── run.sh              # 转发器
│   ├── requirements-ci.txt
└── workflows/
    └── ci.yml              # 工作流外壳
run.sh                      # 根逻辑脚本
```

### `.github/ci/run.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail
CMD="${1:-ci:pg:all}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -x "${ROOT}/run.sh" ]]; then
  exec "${ROOT}/run.sh" "$CMD" "${@:2}"
else
  echo "ERROR: ${ROOT}/run.sh not found or not executable." >&2
  exit 127
fi
```

### `run.sh`（PG on 5433）核心逻辑
```bash
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://wms:wms@127.0.0.1:5433/wms}"

case "${1:-ci:pg:all}" in
  ci:pg:migrate)  alembic upgrade head ;;
  ci:pg:health)   alembic upgrade head; python3 tools/db_invariants.py ;;
  ci:pg:quick)    alembic upgrade head; pytest -q tests/quick -m "not slow" ;;
  ci:pg:smoke)    pytest -q tests/smoke || pytest -q tests/quick/test_inbound_pg.py::test_inbound_receive_and_putaway_integrity ;;
  *) echo "Usage: ./run.sh ci:pg:all"; exit 1 ;;
esac
```

### 统一策略
- 端口固定：**5433**；
- CI job 仅执行 `.github/ci/run.sh ci:pg:all`；
- 所有逻辑均可在本地重现。

✅ CI 与本地环境完全一致。

---

## 五、Step 6｜体检扩展与快照链路完备

### 问题修复要点
- 解决多头迁移 `multiple heads`；
- 修复 `CREATE INDEX CONCURRENTLY` 事务报错；
- 统一列名 `snapshot_date`；
- 解决快照回灌窗口 `(prev_end, cut_end]` 错位。

### 体检脚本扩展
```bash
python scripts/pg_healthcheck.py --dsn postgresql://wms:wms@127.0.0.1:5433/wms --spec scripts/db_spec.json
```
检测唯一约束、外键、索引列序，均 `[OK]`。

### 四大 Quick 测试
| 测试项 | 说明 | 状态 |
|--------|------|------|
| test_inbound_idempotent_pg | 入库幂等 | ✅ |
| test_putaway_move_pg | 出入对称 | ✅ |
| test_stock_snapshot_pg | 快照幂等 | ✅ |
| test_stock_snapshot_backfill_pg | 快照回灌 | ✅ |

### 执行命令
```bash
# 升级 + 体检
alembic upgrade head
python scripts/pg_healthcheck.py --dsn postgresql://wms:wms@127.0.0.1:5433/wms --spec scripts/db_spec.json

# 四测
PYTHONPATH=. pytest -q tests/quick/test_inbound_idempotent_pg.py -s
PYTHONPATH=. pytest -q tests/quick/test_putaway_move_pg.py -s
PYTHONPATH=. pytest -q tests/quick/test_stock_snapshot_pg.py -s
PYTHONPATH=. pytest -q tests/quick/test_stock_snapshot_backfill_pg.py -s
```

✅ 四测全绿，PG 体检绿灯。

---

## 六、线下 ↔ 线上一致性 Checklist

| 项目 | 本地 | CI | 备注 |
|------|------|----|------|
| 数据库端口 | 5433 | 5433 | 一致 |
| DATABASE_URL | `postgresql+psycopg://wms:wms@127.0.0.1:5433/wms` | 同上 | 环境变量对齐 |
| Python 版本 | 3.12.3 | 3.12.11 | ✅ 兼容 |
| Alembic 迁移 | `alembic upgrade head` | 同上 | ✅ |
| Healthcheck | `python scripts/pg_healthcheck.py` | 同上 | ✅ |
| 测试命令 | `pytest -q tests/quick` | `pytest -q tests/quick` | ✅ |
| run.sh | 最新版（UTF-8 强制） | `.github/ci/run.sh` 转发 | ✅ |

### 快速验证
```bash
# 本地快速体检
DATABASE_URL='postgresql+psycopg://wms:wms@127.0.0.1:5433/wms' ./run.sh ci:pg:health

# 快速四测
./run.sh ci:pg:quick
```

✅ 本地与 CI 行为完全一致。

---

## 七、结论与下一步

### 当前状态
- Step 6 结束：迁移、体检、测试、CI 全绿；
- CI 与本地完全一致；
- CI 路由稳定，后续脚本可增量演进。

### 下一步 Step 7 计划
1. CI job 矩阵化（Smoke / Quick / Full / Lint / Coverage）。
2. 独立 Schema 体检 Job，作为 Required Check。
3. 增加性能采样与日志聚合，观察库存写入耗时。
4. 归档 Step 6 → `060_SnapshotService_v1_CI体检全绿.md`。

---

**结论：** WMS-DU 项目自 Step 3 至 Step 6 已实现 PostgreSQL 全链路闭环；CI、迁移、测试、体检四层统一；系统稳定可进入 Step 7 性能分析与可观测性阶段。
