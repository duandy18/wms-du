#!/usr/bin/env bash
set -euo pipefail

DB="${DB:-postgres://wms:wms@127.0.0.1:5433/wms}"

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTBASE="$BASE_DIR/schema_dump"

STAMP="$(date +%Y%m%d_%H%M%S)"
OUTDIR="$OUTBASE/shipping_pricing_$STAMP"

mkdir -p "$OUTDIR"

echo "Audit output -> $OUTDIR"

TABLES=(
shipping_provider_pricing_schemes
shipping_provider_zones
shipping_provider_zone_members
shipping_provider_zone_brackets
shipping_provider_surcharges
pricing_scheme_dest_adjustments
shipping_records
)

echo "=== TABLE STRUCTURES ==="

for t in "${TABLES[@]}"; do
  echo "Dumping $t"
  psql "$DB" -c "\d+ $t" \
  > "$OUTDIR/${t}_structure.txt"
done


echo "=== INDEXES ==="

psql "$DB" <<'SQL' \
> "$OUTDIR/indexes.txt"
SELECT
schemaname,
tablename,
indexname,
indexdef
FROM pg_indexes
WHERE tablename IN (
'shipping_provider_pricing_schemes',
'shipping_provider_zones',
'shipping_provider_zone_members',
'shipping_provider_zone_brackets',
'shipping_provider_surcharges',
'pricing_scheme_dest_adjustments',
'shipping_records'
)
ORDER BY tablename,indexname;
SQL


echo "=== CONSTRAINTS ==="

psql "$DB" <<'SQL' \
> "$OUTDIR/constraints.txt"
SELECT
c.conrelid::regclass AS table_name,
c.conname,
c.contype,
pg_get_constraintdef(c.oid)
FROM pg_constraint c
WHERE c.conrelid::regclass::text IN (
'shipping_provider_pricing_schemes',
'shipping_provider_zones',
'shipping_provider_zone_members',
'shipping_provider_zone_brackets',
'shipping_provider_surcharges',
'pricing_scheme_dest_adjustments',
'shipping_records'
)
ORDER BY table_name,c.contype;
SQL


echo "=== COLUMNS ==="

psql "$DB" <<'SQL' \
> "$OUTDIR/columns.txt"
SELECT
table_name,
ordinal_position,
column_name,
data_type,
udt_name,
is_nullable,
column_default
FROM information_schema.columns
WHERE table_name IN (
'shipping_provider_pricing_schemes',
'shipping_provider_zones',
'shipping_provider_zone_members',
'shipping_provider_zone_brackets',
'shipping_provider_surcharges',
'pricing_scheme_dest_adjustments',
'shipping_records'
)
ORDER BY table_name,ordinal_position;
SQL


echo "=== SAMPLE DATA ==="

for t in "${TABLES[@]}"; do
  psql "$DB" -c "SELECT * FROM $t LIMIT 50" \
  > "$OUTDIR/${t}_sample.txt"
done


echo "=== JSON USAGE ==="

psql "$DB" <<'SQL' \
> "$OUTDIR/json_usage.txt"

SELECT
COUNT(*) AS total,
COUNT(*) FILTER (WHERE segments_json IS NULL) AS segments_null,
COUNT(*) FILTER (WHERE segments_json IS NOT NULL) AS segments_not_null,
COUNT(*) FILTER (WHERE billable_weight_rule IS NULL) AS rule_null,
COUNT(*) FILTER (WHERE billable_weight_rule IS NOT NULL) AS rule_not_null
FROM shipping_provider_pricing_schemes;

SELECT
COUNT(*) AS total,
COUNT(*) FILTER (WHERE price_json IS NULL) AS price_null,
COUNT(*) FILTER (WHERE price_json IS NOT NULL) AS price_not_null
FROM shipping_provider_zone_brackets;

SELECT
COUNT(*) AS total,
COUNT(*) FILTER (WHERE condition_json IS NULL) AS cond_null,
COUNT(*) FILTER (WHERE condition_json IS NOT NULL) AS cond_not_null,
COUNT(*) FILTER (WHERE amount_json IS NULL) AS amt_null,
COUNT(*) FILTER (WHERE amount_json IS NOT NULL) AS amt_not_null
FROM shipping_provider_surcharges;

SQL


echo "=== ZONE MEMBER DISTRIBUTION ==="

psql "$DB" <<'SQL' \
> "$OUTDIR/zone_member_distribution.txt"

SELECT level,COUNT(*)
FROM shipping_provider_zone_members
GROUP BY level
ORDER BY COUNT(*) DESC;

SELECT level,value,COUNT(*)
FROM shipping_provider_zone_members
GROUP BY level,value
ORDER BY COUNT(*) DESC
LIMIT 100;

SQL


echo "=== BRACKET OVERLAP CHECK ==="

psql "$DB" <<'SQL' \
> "$OUTDIR/bracket_overlap.txt"

SELECT
a.zone_id,
a.id,
a.min_kg,
a.max_kg,
b.id,
b.min_kg,
b.max_kg
FROM shipping_provider_zone_brackets a
JOIN shipping_provider_zone_brackets b
ON a.zone_id=b.zone_id
AND a.id<b.id
AND NOT (a.max_kg<=b.min_kg OR b.max_kg<=a.min_kg);

SQL


echo "=== ACTIVE SCHEME CHECK ==="

psql "$DB" <<'SQL' \
> "$OUTDIR/scheme_active_conflict.txt"

SELECT
warehouse_id,
shipping_provider_id,
COUNT(*)
FROM shipping_provider_pricing_schemes
WHERE active=true
AND archived_at IS NULL
GROUP BY warehouse_id,shipping_provider_id
HAVING COUNT(*)>1;

SQL


echo "Audit complete."
echo "Result directory:"
echo "$OUTDIR"
