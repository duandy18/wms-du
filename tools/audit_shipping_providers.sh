#!/usr/bin/env bash
set -euo pipefail

DB_DSN="${DB_DSN:-postgres://wms:wms@127.0.0.1:5433/wms}"

# output only under tools/schema_dump/<timestamp>_shipping_provider_audit
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_ROOT="${BASE_DIR}/schema_dump"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="${OUT_ROOT}/${STAMP}_shipping_provider_audit"

mkdir -p "${OUT_DIR}"

echo "Output: ${OUT_DIR}"
echo "DB_DSN: ${DB_DSN}"
echo

run_psql () {
  local name="$1"
  local sql="$2"
  psql "${DB_DSN}" -v ON_ERROR_STOP=1 <<SQL | nl -ba > "${OUT_DIR}/${name}"
${sql}
SQL
}

run_psql "01_tables_dplus.txt" "
\\d+ shipping_providers
\\d+ warehouse_shipping_providers
\\d+ shipping_records
\\d+ shipping_provider_contacts
\\d+ shipping_provider_pricing_schemes
\\d+ shipping_provider_pricing_scheme_warehouses
\\d+ shipping_provider_zones
\\d+ shipping_provider_zone_members
\\d+ shipping_provider_zone_brackets
\\d+ shipping_provider_surcharges
"

run_psql "02_constraints.txt" "
SELECT
  t.relname AS table_name,
  c.conname AS constraint_name,
  c.contype,
  pg_get_constraintdef(c.oid) AS def
FROM pg_constraint c
JOIN pg_class t ON t.oid = c.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname='public'
  AND t.relname IN (
    'shipping_providers',
    'warehouse_shipping_providers',
    'shipping_records',
    'shipping_provider_contacts',
    'shipping_provider_pricing_schemes',
    'shipping_provider_pricing_scheme_warehouses',
    'shipping_provider_zones',
    'shipping_provider_zone_members',
    'shipping_provider_zone_brackets',
    'shipping_provider_surcharges'
  )
ORDER BY table_name, contype, constraint_name;
"

run_psql "03_indexes.txt" "
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname='public'
  AND tablename IN (
    'shipping_providers',
    'warehouse_shipping_providers',
    'shipping_records',
    'shipping_provider_contacts',
    'shipping_provider_pricing_schemes',
    'shipping_provider_pricing_scheme_warehouses',
    'shipping_provider_zones',
    'shipping_provider_zone_members',
    'shipping_provider_zone_brackets',
    'shipping_provider_surcharges'
  )
ORDER BY tablename, indexname;
"

run_psql "04_health_checks.txt" "
-- provider code normalization
SELECT
  COUNT(*) AS total,
  COUNT(DISTINCT code) AS distinct_code,
  COUNT(DISTINCT upper(btrim(code))) AS distinct_norm_code
FROM shipping_providers;

-- duplicate names (warning only)
SELECT name, COUNT(*) cnt
FROM shipping_providers
GROUP BY 1
HAVING COUNT(*) > 1
ORDER BY cnt DESC, name
LIMIT 50;

-- duplicate warehouse-provider binding (should be empty)
SELECT warehouse_id, shipping_provider_id, COUNT(*)
FROM warehouse_shipping_providers
GROUP BY 1,2
HAVING COUNT(*) > 1;

-- duplicate tracking per provider (should be empty)
SELECT shipping_provider_id, tracking_no, COUNT(*)
FROM shipping_records
WHERE tracking_no IS NOT NULL
GROUP BY 1,2
HAVING COUNT(*) > 1;
"

echo "Done."
echo "Result dir: ${OUT_DIR}"
