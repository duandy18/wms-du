## Canvas 文档：WMS-DU 项目 CI 转发器与老路由脚本设计讨论

### 一、背景
用户当前在 WMS-DU 项目中使用 GitHub Actions 进行 CI/CD 管理。项目规模较小、为单人多机开发模式，已有工作流 `.github/workflows/ci.yml`。用户希望保持 CI 稳定、简洁，不频繁修改 YAML 配置，同时提升可维护性。

---

### 二、总体设计理念

> 策略：**少动 CI，多用 run.sh。**

1. **CI 仅作外壳**：保持 YAML 文件中的 Job 名、结构、Required Checks 稳定。
2. **核心逻辑沉入脚本**：统一到仓库根的 `run.sh` 中进行迁移、体检、测试等调度。
3. **引入转发器 `.github/ci/run.sh`**：作为 CI 的固定入口，起到“中转层”作用。
4. **run.sh 负责执行全部逻辑**：包括 Alembic 迁移、pg_health 检查、pytest quick/smoke 测试、关键不变量断言等。

---

### 三、文件结构

```
.github/
├── ci/
│   ├── run.sh              # ✅ 转发器：固定入口，转发到仓库根 run.sh
│   ├── requirements-ci.txt
│   ├── run (1).sh
│   └── run.sh.bak
└── workflows/
    ├── ci_bootstrap_shadow.yml
    └── ci.yml              # 工作流文件，保持稳定
run.sh                      # ✅ 项目根：老路由逻辑脚本
```

---

### 四、转发器 `.github/ci/run.sh`

```bash
#!/usr/bin/env bash
# CI 转发器：固定入口，不承载任何业务逻辑，仅把 CI 的调用转发到仓库根 run.sh
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

**说明：**
- CI 永远只需调用 `.github/ci/run.sh`，后续逻辑可随时在根目录的 `run.sh` 调整。
- 这样 Job 名稳定，Required Checks 不会因为逻辑变化而抖动。

---

### 五、仓库根 `run.sh`（老路由固定流程，端口 5433）

```bash
#!/usr/bin/env bash
# 老路由：每次固定跑四件套（迁移 → 体检 → quick → smoke）
set -euo pipefail

log(){ printf "\n[%s] %s\n" "$(date +'%H:%M:%S')" "$*"; }

wait_pg(){
  local h="${1:-127.0.0.1}" p="${2:-5433}" u="${3:-wms}" d="${4:-wms}"
  if command -v pg_isready >/dev/null 2>&1; then
    for _ in $(seq 1 60); do
      if pg_isready -h "$h" -p "$p" -U "$u" -d "$d" >/dev/null 2>&1; then
        return 0
      fi
      sleep 1
    done
    echo "Postgres not ready after 60s" >&2
    exit 2
  fi
}

# 迁移
 task_pg_migrate(){
  log "Alembic upgrade -> head"
  wait_pg 127.0.0.1 5433 wms wms || true
  alembic upgrade head
}

# 健康检查 + 不变量断言
 task_pg_health(){
  log "PG healthcheck (strict)"
  mkdir -p pg_health
  if [ -f tools/pg_healthcheck.py ]; then
    python tools/pg_healthcheck.py --strict --output pg_health/report.json
  else
    python - <<'PY'
print("WARN: tools/pg_healthcheck.py missing; skipping strict checks")
PY
  fi
  # ===== 关键不变量断言（语义级检查） =====
  python - <<'PY'
import os, sys
from sqlalchemy import create_engine, text
url = os.environ.get("DATABASE_URL")
if not url:
    sys.exit(0)
eng = create_engine(url.replace("+psycopg", ""))
with eng.begin() as c:
    errors = []
    # 1) stocks(item_id, location_id) 唯一约束
    uniques = c.execute(text("""
        SELECT pg_get_constraintdef(c.oid) AS def
        FROM pg_constraint c
        WHERE c.conrelid = 'public.stocks'::regclass
          AND c.contype = 'u'
    """)).fetchall()
    has_uq = any(
        ("UNIQUE (" in r.def and "item_id" in r.def and "location_id" in r.def)
        for r in uniques)
    if not has_uq:
        errors.append("缺少 stocks(item_id, location_id) 的唯一约束。")
    # 2) stock_ledger.stock_id → stocks.id 外键
    fks = c.execute(text("""
        SELECT pg_get_constraintdef(c.oid) AS def
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_class r ON r.oid = c.confrelid
        WHERE c.contype = 'f'
          AND t.relname = 'stock_ledger'
          AND r.relname = 'stocks'
    """)).fetchall()
    has_fk = any("(stock_id)" in r.def and "REFERENCES public.stocks(id)" in r.def for r in fks)
    if not has_fk:
        errors.append("缺少 stock_ledger(stock_id) → stocks(id) 的外键。")
    # 输出结果
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        sys.exit(2)
    else:
        print("DB invariants OK: stocks 唯一 + ledger 外键")
PY
  # ===== 不变量断言结束 =====
}

# quick/smoke 测试
 task_quick(){ log "pytest quick"; pytest -q tests/quick -m "not slow" --maxfail=1 --durations=10; }
 task_smoke(){
  log "pytest smoke"
  if [ -d tests/smoke ]; then
    pytest -q tests/smoke --maxfail=1 --durations=10
  else
    pytest -q \
      tests/quick/test_inbound_pg.py::test_inbound_receive_and_putaway_integrity \
      tests/quick/test_putaway_pg.py::test_putaway_integrity \
      -s --maxfail=1 --durations=10
  fi
}

case "${1:-ci:pg:all}" in
  ci:pg:migrate) task_pg_migrate ;;
  ci:pg:health)  task_pg_migrate; task_pg_health ;;
  ci:pg:quick)   task_pg_migrate; task_pg_health; task_quick ;;
  ci:pg:smoke)   task_pg_migrate; task_pg_health; task_smoke ;;
  ci:pg:all)     task_pg_migrate; task_pg_health; task_quick; task_smoke ;;
  *) cat <<'USAGE'
Usage:
  ./run.sh ci:pg:all      # 迁移→体检→quick→smoke（主入口）
  ./run.sh ci:pg:migrate  # 仅迁移
  ./run.sh ci:pg:health   # 迁移 + 体检
  ./run.sh ci:pg:quick    # 迁移 + 体检 + quick
  ./run.sh ci:pg:smoke    # 迁移 + 体检 + smoke
USAGE
     exit 1 ;;
esac
```

---

### 六、CI 调用方式（ci.yml）

只需保证执行行如下：
```yaml
- name: Run CI
  run: bash .github/ci/run.sh ci:pg:all
```
其他 Job 名、workflow 名保持不变。

---

### 七、关键点回顾
1. `.github/ci/run.sh` 是 **转发层**：稳定入口，CI 只认它。
2. `run.sh` 是 **逻辑层**：四件套流程 + 不变量检查。
3. **不变量断言**：
   - 检查 `stocks(item_id, location_id)` 唯一约束是否存在；
   - 检查 `stock_ledger.stock_id` 外键是否存在；
   - 可选检查 `(item_id, location_id)` 索引。
4. 端口统一为 5433。

---

### 八、实施步骤
1. 新建分支 `chore/ci-forwarder`；
2. 添加 `.github/ci/run.sh`；
3. 添加或覆盖根目录 `run.sh`；
4. 修改 `.github/workflows/ci.yml` 的执行命令；
5. 提交并 PR；
6. CI 验证通过后合入 main。

---

### 九、效果
- CI 稳定：Required Checks 不抖。
- CI 可回退：只需改 `run.sh`。
- CI 可复现：本地运行命令与 Actions 完全一致。
- 项目结构更清晰：YAML 负责触发，脚本负责逻辑。
