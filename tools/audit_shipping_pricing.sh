#!/usr/bin/env bash
set -euo pipefail

# ==========================================
# Shipping pricing schema audit
# ==========================================
# Usage:
#   cd tools
#   ./audit_shipping_pricing.sh
#
# Optional:
#   DB_DSN="postgres://user:pass@host:port/db" ./audit_shipping_pricing.sh
#
# Output:
#   tools/schema_dump/<timestamp>_shipping_pricing/
# ==========================================

DB_DSN="${DB_DSN:-postgres://wms:wms@127.0.0.1:5433/wms}"

TS="$(date +"%Y%m%d_%H%M%S")"
OUT_DIR="schema_dump/${TS}_shipping_pricing"

mkdir -p "$OUT_DIR"

echo "DB: $DB_DSN"
echo "OUT: $OUT_DIR"

TABLES=(
  shipping_providers
  warehouse_shipping_providers
  shipping_provider_pricing_schemes
  shipping_provider_zones
  shipping_provider_zone_brackets
  shipping_records
)

echo "=== Dump table structures ==="
for t in "${TABLES[@]}"; do
  echo "  -> $t"
  psql "$DB_DSN" -c "\d+ $t" >"$OUT_DIR/${t}.txt"
done

echo "=== Dump indexes ==="
for t in "${TABLES[@]}"; do
  psql "$DB_DSN" -c "
SELECT
  indexname,
  indexdef
FROM pg_indexes
WHERE tablename = '$t'
ORDER BY indexname;
" >"$OUT_DIR/${t}_indexes.sql"
done

echo "=== Dump constraints ==="
# Build SQL literal array: ARRAY['t1','t2',...]
TABLES_SQL="$(printf "'%s'," "${TABLES[@]}")"
TABLES_SQL="${TABLES_SQL%,}"

psql "$DB_DSN" -c "
SELECT
  conrelid::regclass::text AS table_name,
  conname,
  pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid::regclass::text = ANY (ARRAY[$TABLES_SQL])
ORDER BY conrelid::regclass::text, conname;
" >"$OUT_DIR/constraints.sql"

echo "=== Dump foreign keys ==="
psql "$DB_DSN" -c "
SELECT
  tc.table_name,
  kcu.column_name,
  ccu.table_name AS foreign_table,
  ccu.column_name AS foreign_column
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_name = ANY (ARRAY[$TABLES_SQL])
ORDER BY tc.table_name, kcu.ordinal_position;
" >"$OUT_DIR/foreign_keys.sql"

echo "=== DONE ==="
echo "Output: $OUT_DIR"
