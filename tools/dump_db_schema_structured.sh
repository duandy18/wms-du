#!/usr/bin/env bash
set -euo pipefail

DSN="${1:-postgres://wms:wms@127.0.0.1:5433/wms}"
OUT_DIR="${2:-tools/schema_dump}"
TS="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$OUT_DIR/$TS"

psql_cmd() {
  psql "$DSN" -v ON_ERROR_STOP=1 -X -P pager=off "$@"
}

echo "[dump] DSN=$DSN"
echo "[dump] OUT=$OUT_DIR/$TS"

# ============================================================
# 核心对象集合（按“你库的真名”收口）
#
# Phase 2（已完成）：Item 主数据收敛
# - items / item_uoms / item_barcodes / lots
#
# Phase 3+（本阶段）：基础主数据域扩展（stores / shipping_providers ...）
# - 先纳入结构与约束审计，后续逐域收敛合同与语义边界
#
# 采购入库：purchase_orders / purchase_order_lines / inbound_receipts / inbound_receipt_lines
# 库存域：stock_ledger / stock_snapshots / stocks_lot / inventory_movements
# 出库域：internal_outbound_docs / internal_outbound_lines / outbound_*（v2 为主）
# 视图：v_stocks_lot_reconcile_receipt / vw_outbound_metrics（用于对账与指标）
#
# 脚本会过滤不存在的对象（表/视图/物化视图/分区父表），避免炸。
# ============================================================
OBJECTS=(
  # ----------------------------------------------------------
  # master data (item)
  # ----------------------------------------------------------
  items
  item_uoms
  item_barcodes
  lots

  # ----------------------------------------------------------
  # master data (foundation domains) - real table names in this DB
  # shops / stores
  # ----------------------------------------------------------
  stores
  platform_shops
  platform_test_shops
  store_tokens
  store_warehouse
  store_province_routes

  # warehouses / suppliers
  warehouses
  suppliers

  # shipping providers (carriers / express / logistics)
  shipping_providers
  warehouse_shipping_providers
  shipping_provider_contacts

  # shipping pricing（终态主线）
  shipping_provider_pricing_schemes
  shipping_provider_pricing_scheme_segments
  shipping_provider_destination_groups
  shipping_provider_destination_group_members
  shipping_provider_pricing_matrix
  shipping_provider_surcharges

  # ----------------------------------------------------------
  # purchase / inbound
  # ----------------------------------------------------------
  purchase_orders
  purchase_order_lines
  inbound_receipts
  inbound_receipt_lines

  # ----------------------------------------------------------
  # inventory domain
  # ----------------------------------------------------------
  stock_ledger
  stock_snapshots
  stocks_lot
  inventory_movements

  # ----------------------------------------------------------
  # internal outbound (doc/lines)
  # ----------------------------------------------------------
  internal_outbound_docs
  internal_outbound_lines

  # ----------------------------------------------------------
  # outbound domain (v2)
  # ----------------------------------------------------------
  outbound_commits_v2
  outbound_lines_v2
  outbound_ship_ops

  # ----------------------------------------------------------
  # outbound (legacy/other, keep for audit)
  # ----------------------------------------------------------
  outbound_commits

  # ----------------------------------------------------------
  # views
  # ----------------------------------------------------------
  v_stocks_lot_reconcile_receipt
  vw_outbound_metrics
)

psql_cmd -Atc "SELECT version();" > "$OUT_DIR/$TS/00_pg_version.txt"
psql_cmd -Atc "SHOW server_version;" > "$OUT_DIR/$TS/00_server_version.txt"
psql_cmd -Atc "SHOW search_path;" > "$OUT_DIR/$TS/00_search_path.txt"
psql_cmd -Atc "SELECT current_database(), current_user;" > "$OUT_DIR/$TS/00_whoami.txt"

REQ_FILE="$OUT_DIR/$TS/00_objects_requested.txt"
printf "%s\n" "${OBJECTS[@]}" > "$REQ_FILE"

REQ_SQL_LIST="$(printf "'%s'," "${OBJECTS[@]}" | sed 's/,$//')"

EXIST_FILE="$OUT_DIR/$TS/00_objects_existing.txt"
psql_cmd -Atc "
WITH want AS (
  SELECT unnest(ARRAY[$REQ_SQL_LIST]) AS name
),
pool AS (
  SELECT n.nspname AS schema, c.relname AS name, c.relkind
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname NOT IN ('pg_catalog','information_schema')
    AND c.relkind IN ('r','p','v','m')
)
SELECT w.name
FROM want w
JOIN pool p ON p.schema='public' AND p.name=w.name
ORDER BY w.name;
" > "$EXIST_FILE"

mapfile -t OBJECTS < "$EXIST_FILE"

echo "[dump] objects_requested=$(wc -l < "$REQ_FILE") objects_existing=$(wc -l < "$EXIST_FILE")"

if [ "${#OBJECTS[@]}" -eq 0 ]; then
  echo "[dump] ERROR: none of requested objects exist in public schema. See $REQ_FILE" >&2
  exit 1
fi

EXIST_SQL_LIST="$(printf "'%s'," "${OBJECTS[@]}" | sed 's/,$//')"

{
  echo "\\x on"
  for o in "${OBJECTS[@]}"; do
    echo "\\echo '==================== \\d+ $o ===================='"
    echo "\\d+ $o"
    echo ""
  done
} | psql_cmd > "$OUT_DIR/$TS/01_describe_d_plus.txt"

psql_cmd -c "
WITH target AS (
  SELECT c.oid, c.relname
  FROM pg_class c
  JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname='public'
    AND c.relkind IN ('r','p')
    AND c.relname = ANY (ARRAY[$EXIST_SQL_LIST])
)
SELECT
  conrelid::regclass AS table_name,
  conname,
  contype,
  pg_get_constraintdef(pg_constraint.oid) AS def
FROM pg_constraint
WHERE conrelid IN (SELECT oid FROM target)
ORDER BY conrelid::regclass::text, contype, conname;
" > "$OUT_DIR/$TS/02_constraints.txt"

psql_cmd -c "
SELECT
  tablename,
  indexname,
  indexdef
FROM pg_indexes
WHERE schemaname='public'
  AND tablename = ANY (ARRAY[$EXIST_SQL_LIST])
ORDER BY tablename, indexname;
" > "$OUT_DIR/$TS/03_indexes.txt"

psql_cmd -c "
SELECT
  tc.table_name,
  kcu.column_name,
  ccu.table_name AS foreign_table_name,
  ccu.column_name AS foreign_column_name,
  tc.constraint_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
  AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
  AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema='public'
  AND tc.table_name = ANY (ARRAY[$EXIST_SQL_LIST])
ORDER BY tc.table_name, tc.constraint_name, kcu.ordinal_position;
" > "$OUT_DIR/$TS/04a_fks_outbound.txt"

psql_cmd -c "
SELECT
  tc.table_name AS referencing_table,
  kcu.column_name AS referencing_column,
  ccu.table_name AS referenced_table,
  ccu.column_name AS referenced_column,
  tc.constraint_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
  AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
  AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema='public'
  AND ccu.table_name = ANY (ARRAY[$EXIST_SQL_LIST])
ORDER BY referenced_table, referencing_table, tc.constraint_name, kcu.ordinal_position;
" > "$OUT_DIR/$TS/04b_fks_inbound.txt"

psql_cmd -c "
SELECT
  table_name,
  ordinal_position,
  column_name,
  data_type,
  udt_name,
  is_nullable,
  column_default
FROM information_schema.columns
WHERE table_schema='public'
  AND table_name = ANY (ARRAY[$EXIST_SQL_LIST])
ORDER BY table_name, ordinal_position;
" > "$OUT_DIR/$TS/05_columns.txt"

psql_cmd -c "
SELECT t.typname AS enum_type, e.enumlabel AS enum_label, e.enumsortorder
FROM pg_type t
JOIN pg_enum e ON t.oid = e.enumtypid
ORDER BY t.typname, e.enumsortorder;
" > "$OUT_DIR/$TS/06_enums.txt"

psql_cmd -c "
SELECT
  tgrelid::regclass AS table_name,
  tgname,
  pg_get_triggerdef(t.oid) AS trigger_def
FROM pg_trigger t
WHERE NOT t.tgisinternal
  AND tgrelid::regclass::text = ANY (ARRAY[$EXIST_SQL_LIST])
ORDER BY tgrelid::regclass::text, tgname;
" > "$OUT_DIR/$TS/07_triggers.txt"

psql_cmd -c "
SELECT table_name, view_definition
FROM information_schema.views
WHERE table_schema='public'
ORDER BY table_name;
" > "$OUT_DIR/$TS/08_views.txt"

{
  echo "DSN=$DSN"
  echo "TIME=$TS"
  echo ""
  echo "OBJECTS_REQUESTED:"
  cat "$REQ_FILE"
  echo ""
  echo "OBJECTS_EXISTING:"
  cat "$EXIST_FILE"
  echo ""
  echo "FILES:"
  ls -1 "$OUT_DIR/$TS"
} > "$OUT_DIR/$TS/README.txt"

echo "[dump] done -> $OUT_DIR/$TS"
echo "[dump] tip: cd $OUT_DIR/$TS && less 01_describe_d_plus.txt"
