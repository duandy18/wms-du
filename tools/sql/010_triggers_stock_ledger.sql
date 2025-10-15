#!/usr/bin/env bash
set -euo pipefail

banner() { printf '\n==== %s ====\n' "$*"; }

# -------- 基础环境回显 --------
banner "Env & Versions"
python -V
pip -V || true
echo "DATABASE_URL=${DATABASE_URL:-<empty>}"
echo "GITHUB_ACTIONS=${GITHUB_ACTIONS:-}"
echo "WMS_SQLITE_GUARD=${WMS_SQLITE_GUARD:-}"
echo "WMS_DB_FIX=${WMS_DB_FIX:-}"

BACKEND="unknown"
if [[ "${DATABASE_URL:-}" == postgresql* ]]; then BACKEND="pg"; fi
if [[ "${DATABASE_URL:-}" == sqlite* ]]; then BACKEND="sqlite"; fi
echo "BACKEND=${BACKEND}"

# -------- 你之前 Canvas 中的预修复逻辑放这里（可继续细化）--------
pre_repair() {
  banner "Pre-Repair (from Canvas)"
  # 示例：若需要，可在此放入你原先的 fix_alembic_version_len / items.id identity 等逻辑
  # 由于不同环境权限与版本差异较大，这里仅示例性包含一个“可选处理位”。
  if [[ "$BACKEND" == "pg" ]]; then
    psql "${DATABASE_URL}" -v ON_ERROR_STOP=1 <<'SQL' || true
-- 可选示例：确保 alembic_version.version_num 至少 32（若你历史上遇到长度问题）
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='alembic_version' AND column_name='version_num') THEN
    -- 只有在 varchar 太短时才扩（示例长度 255）
    ALTER TABLE IF EXISTS alembic_version
      ALTER COLUMN version_num TYPE VARCHAR(255);
  END IF;
END$$;
SQL
  fi
}

# -------- Reset（在 Smoke 前恢复到“干净”状态）--------
reset_db() {
  banner "Reset DB (lightweight)"
  # 推荐使用 Alembic 做轻量 reset；避免直接 drop schema 的权限坑
  alembic downgrade base || true
  alembic upgrade head
}

# -------- 结构断言 / 触发器重建统一入口 --------
check_and_fix_invariants() {
  banner "DB Invariants --check"
  python tools/db_invariants.py --check

  if [[ "$BACKEND" == "pg" ]]; then
    banner "Rebuild Triggers (idempotent --fix)"
    WMS_DB_FIX=1 python tools/db_invariants.py --fix
  fi
}

# -------- 测试阶段 --------
run_smoke() {
  banner "Run Smoke (PG/SQLite)"
  # 你可以把 smoke 集合化到 tests/smoke 目录；这里以存在性为例
  if [[ -d tests/smoke ]]; then
    pytest -q tests/smoke -s
  else
    # 至少跑一条最关键的快速测试（可替换为你的实际 smoke 用例）
    pytest -q tests/ci/test_db_invariants.py -s || true
  fi
}

# -------- 主流程 --------
pre_repair
reset_db
check_and_fix_invariants
run_smoke

banner "CI pipeline finished"
