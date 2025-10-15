### 《Step 5：数据库唯一约束加固与幂等验证（WMS-DU）》

---

#### 📘 摘要
本阶段完成了 WMS-DU 项目的 **Step 5 数据库加固与幂等验证**，目标是让核心数据表在 PostgreSQL 中具备结构级防重与幂等保障。

主要成果包括：
1. **数据库约束加固**：为 `stock_ledger` 与 `batches` 增加唯一约束，彻底消除历史重复数据；
2. **幂等回放测试**：新增 Quick 用例验证 `PutawayService.bulk_putaway()` 的幂等行为；
3. **CI 四件套验证通过**：迁移、体检、Quick 与 Smoke 测试全绿。

---

#### 🧩 主要改动文件
| 文件路径 | 功能说明 |
|-----------|-----------|
| `alembic/versions/20251014_uq_ledger_reason_ref_refline.py` | 增加 `stock_ledger(reason, ref, ref_line)` 唯一约束，兼容历史 PUTAWAY 记录（右腿 +1 修复）。 |
| `alembic/versions/20251014_uq_batches_composite.py` | 增加 `batches(item_id, warehouse_id, location_id, batch_code, production_date, expiry_date)` 复合唯一约束，修正重复批次并更新 FK。 |
| `tests/quick/test_putaway_idempotency_pg.py` | 新增幂等 Quick 测试，验证 `PutawayService.bulk_putaway()` 的重复执行不会重复写账或影响库存。 |
| `tools/ensure_pg_ledger_shape.py` | 扩展体检脚本，检测上述两个新 UNIQUE 约束。 |
| `pytest.ini` | 注册 `quick` 标记，设置 `asyncio_mode=auto`。 |

---

#### ⚙️ 迁移与验证过程

**1. 迁移执行顺序**：
```
737276e10020 → 20251014_uq_ledger_reason_ref_refline → 20251014_uq_batches_composite
```

**2. 执行命令：**
```bash
alembic upgrade head
bash .github/ci/run.sh ci:pg:all
```

**3. 结果：**
- Alembic 迁移执行成功 ✅
- Verify-Ledger 体检 `[OK]`
- Quick 全部测试通过 ✅
- Smoke API 返回 200 ✅

---

#### 🧪 解决的核心问题
1. **事务内建索引错误**：
   - 解决方式：使用 `autocommit_block()` 在事务外执行 `CREATE INDEX`。
2. **CTE 可见性问题**：
   - 解决方式：拆分为两个独立的 CTE 语句，分别用于 `UPDATE` 与 `DELETE`。
3. **未注册 pytest 标记警告**：
   - 解决方式：在 `pytest.ini` 中注册 `markers = quick`。
4. **异步 fixture 严格模式警告**：
   - 解决方式：改用 `@pytest_asyncio.fixture`。
5. **Pydantic V2 Config 弃用警告**：
   - 处理方式：暂时通过 `filterwarnings` 抑制，未来迁移为 `ConfigDict`。

---

#### ✅ CI 输出摘要
```bash
[ci:pg:migrate] ✅
[ci:pg:verify-ledger] [OK] ledger/stocks shape valid
[ci:pg:quick] ✅ 全部测试通过
[ci:pg:smoke] ✅ HTTP 200 响应
```

---

#### 📈 当前系统状态
- **迁移链**：`737276e10020 → ledger UQ → batches UQ` 完整执行；
- **体检**：列 / 类型 / 外键 / 唯一约束全覆盖；
- **Quick 测试**：入库针刺、批次完整性、并发 putaway、幂等回放全绿；
- **Smoke**：接口链路运行正常。

---

#### 🔧 建议的后续改进
1. **Putaway 日志增强**：增加 worker / claimed / moved 指标日志，便于压测分析；
2. **体检脚本扩展**：检查唯一约束列顺序与索引结构一致性；
3. **Pydantic 迁移**：升级 schemas 为 `ConfigDict` 格式；
4. **Step 6 规划**：设计 `StockSnapshot` 周期汇总与性能分析。

---

#### 🔗 Git 提交流程
```bash
git checkout -b chore/step5-hardening-uniques
git add alembic/versions/*.py tests/quick/test_putaway_idempotency_pg.py tools/ensure_pg_ledger_shape.py
git commit -m "DB hardening: ledger & batch uniques; idempotency quick; shape check extended"
git push -u origin chore/step5-hardening-uniques
# gh pr create --fill --base main --head chore/step5-hardening-uniques
```

---

#### 🧭 续聊方向
1. 体检脚本的唯一约束列序比对与索引校验；
2. Putaway 与 Inbound 的性能日志与监控；
3. Step 6：库存快照周期化与趋势分析方案设计。
