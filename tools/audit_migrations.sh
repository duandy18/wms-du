#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
VERS="$ROOT/alembic/versions"

red() { printf "\033[31m%s\033[0m\n" "$*"; }
yel() { printf "\033[33m%s\033[0m\n" "$*"; }
grn() { printf "\033[32m%s\033[0m\n" "$*"; }
hr()  { printf "\n----------------------------------------\n"; }

if [ ! -d "$VERS" ]; then
  red "找不到 $VERS 目录；请在项目根目录下运行，或传入根路径参数。"
  exit 1
fi

hr
grn "[1/5] 扫描数组参数绑定（CI 高危：unnest(:param) / ANY(:param)）"
hr
# 捕获：unnest(:...) 或 ANY(:...)
grep -RIn -E 'unnest\([^)]*:[A-Za-z_][A-Za-z0-9_]*' "$VERS" || true
grep -RIn -E 'ANY\(\s*:[A-Za-z_][A-Za-z0-9_]*\s*\)'  "$VERS" || true

hr
grn "[2/5] 扫描关键表的无守卫 DDL（ALTER/DROP）"
hr
# 这些最好用 DO $$ + information_schema/pg_catalog 守卫；这里仅报告
grep -RIn -E 'ALTER TABLE\s+.*\s+(orders|batches|stock_ledger|event_log|event_error_log)\b' "$VERS" | grep -v to_regclass || true
grep -RIn -E 'DROP (INDEX|TABLE|VIEW)\b(?!.*IF EXISTS)' "$VERS" || true

hr
grn "[3/5] 自动修复：DROP INDEX → DROP CONSTRAINT（已知在 CI 报 DependentObjectsStillExist 的两类）"
hr

fix_idx_to_constraint() {
  local file="$1"
  local pat="$2"      # 例如 public.uq_ledger_reason_ref_refline_stock
  local table="$3"    # 例如 stock_ledger
  local cname="$4"    # 例如 uq_ledger_reason_ref_refline_stock

  if grep -q "DROP INDEX IF EXISTS[[:space:]]\+$pat" "$file"; then
    cp "$file" "$file.bak.idx2constr" 2>/dev/null || true
    sed -i "s|DROP INDEX IF EXISTS[[:space:]]\+$pat|ALTER TABLE ${table} DROP CONSTRAINT IF EXISTS ${cname}|g" "$file"
    yel "  [改写] $file: DROP INDEX -> DROP CONSTRAINT ON ${table} (${cname})"
  fi
}

# 1) stock_ledger 的唯一键索引（应删约束，不是删索引）
for f in "$VERS"/*.py; do
  fix_idx_to_constraint "$f" "public\.uq_ledger_reason_ref_refline_stock" "stock_ledger" "uq_ledger_reason_ref_refline_stock"
done

# 2) batches 的唯一键索引
for f in "$VERS"/*.py; do
  fix_idx_to_constraint "$f" "public\.uq_batches_item_wh_loc_code" "batches" "uq_batches_item_wh_loc_code"
done

grn "  [OK] 索引类 DROP 的易错点已自动修复（如有匹配）。备份 *.bak.idx2constr 已生成。"

hr
grn "[4/5] 给出守卫模板（人工粘贴）"
hr
cat <<'TEMPLATE'

[模板 A] 对关键表加守卫（示例：orders）
------------------------------------------------
conn = op.get_bind()
conn.execute(sa.text("""
DO $$
BEGIN
  IF to_regclass('public.orders') IS NOT NULL THEN
    -- 在这里写你的 ALTER（例如）
    -- IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    --   WHERE table_schema='public' AND table_name='orders' AND column_name='updated_at') THEN
    --   ALTER TABLE public.orders ADD COLUMN updated_at timestamptz DEFAULT now();
    -- END IF;
  END IF;
END $$;
"""))

[模板 B] 删除列前先删依赖视图（示例：event_error_log.occurred_at）
------------------------------------------------
conn.execute(sa.text("""
DO $$
BEGIN
  IF to_regclass('public.v_event_errors_pending') IS NOT NULL THEN
    EXECUTE 'DROP VIEW IF EXISTS public.v_event_errors_pending CASCADE';
  END IF;
  IF to_regclass('public.v_scan_errors_recent') IS NOT NULL THEN
    EXECUTE 'DROP VIEW IF EXISTS public.v_scan_errors_recent CASCADE';
  END IF;
END $$;
"""));
-- 然后再 ALTER TABLE ... DROP COLUMN IF EXISTS occurred_at;

[模板 C] 避免 unnest(:cols)/ANY(:arr)，用动态 SQL 构数组字面量
------------------------------------------------
-- Python 中拼 'ARRAY['||quote_ident(...)||','||...||']::text[]' 再 EXECUTE
-- 或直接 information_schema 判定列是否齐全以替代数组比较。

TEMPLATE

hr
grn "[5/5] 推荐接下来的校验序列（在项目根目录执行）"
hr
cat <<'NEXT'
alembic downgrade base
alembic upgrade head
alembic downgrade -1 || true
alembic upgrade head

# 快速烟测 /scan
PYTHONPATH=. pytest -q tests/api/test_scan_gateway_pick_probe.py -s
PYTHONPATH=. pytest -q tests/api/test_scan_gateway_pick_commit.py -s
PYTHONPATH=. pytest -q tests/api/test_scan_gateway_putaway_commit.py -s
PYTHONPATH=. pytest -q tests/api/test_scan_gateway_count_commit.py -s
NEXT

grn "[完成] 审计已输出；小范围自动修复已执行。请按上方模板补上剩余守卫。"
