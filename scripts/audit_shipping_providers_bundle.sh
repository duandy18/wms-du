#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   DB_DSN='postgres://wms:wms@127.0.0.1:5433/wms' bash scripts/audit_shipping_providers_bundle.sh
#
# Default DSN (change if needed):
DB_DSN="${DB_DSN:-postgres://wms:wms@127.0.0.1:5433/wms}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT}/tmp/shipping_providers_audit_$(date +%Y%m%d_%H%M%S)"
mkdir -p "${OUT_DIR}"

echo "[audit] output dir: ${OUT_DIR}"
echo "[audit] DB_DSN: ${DB_DSN}"

# ----------------------------
# 1) psql structure dumps
# ----------------------------
psql_dump() {
  local name="$1"
  local sql="$2"
  echo "[audit] psql: ${name}"
  psql "${DB_DSN}" -v ON_ERROR_STOP=1 <<SQL | nl -ba > "${OUT_DIR}/${name}"
${sql}
SQL
}

psql_dump "01_tables_dplus.txt" "\
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

psql_dump "02_constraints.txt" "\
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

psql_dump "03_indexes.txt" "\
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

psql_dump "04_data_health_checks.txt" "\
-- provider.code normalization check
SELECT
  COUNT(*) AS total,
  COUNT(DISTINCT code) AS distinct_code,
  COUNT(DISTINCT upper(btrim(code))) AS distinct_norm_code
FROM shipping_providers;

-- duplicate names (if any)
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

# ----------------------------
# 2) Codebase greps (rg)
# ----------------------------
echo "[audit] rg scans"
(
  cd "${ROOT}"
  rg -n "shipping_provider_id|provider_code|carrier_code|shipping_providers\.code|FROM shipping_providers WHERE code|uq_shipping_records_provider_tracking_notnull" app -S || true
) | nl -ba > "${OUT_DIR}/05_rg_app_shipping_identity.txt"

(
  cd "${ROOT}"
  rg -n "shipping_provider_pricing|pricing_schemes|zones|surcharges|warehouse_shipping_providers" app -S || true
) | nl -ba > "${OUT_DIR}/06_rg_app_shipping_pricing.txt"

# ----------------------------
# 3) Package
# ----------------------------
tar -czf "${OUT_DIR}.tar.gz" -C "$(dirname "${OUT_DIR}")" "$(basename "${OUT_DIR}")"
echo "[audit] bundle created: ${OUT_DIR}.tar.gz"
echo "[audit] done"
