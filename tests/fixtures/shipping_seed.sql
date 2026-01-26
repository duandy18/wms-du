-- tests/fixtures/shipping_seed.sql
-- 目标：让 pricing quote / zone brackets unique&copy 相关测试有最小可用数据
-- 策略：
-- - 幂等：尽量用固定 name，并在存在时复用；避免每次测试产生脏数据
-- - 最小：1 provider / 1 scheme / 1 zone / 2 brackets
--
-- Phase 6 刚性契约补丁：
-- - shipping_providers.warehouse_id NOT NULL
-- - 因此 seed 时必须补 warehouse_id（取 warehouses 最小 id 作为测试锚点）

-- 1) provider
WITH wh AS (
  SELECT id FROM warehouses ORDER BY id ASC LIMIT 1
),
sp AS (
  INSERT INTO shipping_providers (name, code, active, priority, warehouse_id)
  SELECT 'UT-SP-1', 'UT-SP-1', TRUE, 100, wh.id
  FROM wh
  ON CONFLICT (name) DO UPDATE
    SET active = TRUE,
        warehouse_id = EXCLUDED.warehouse_id
  RETURNING id
),
sp2 AS (
  SELECT id FROM sp
  UNION ALL
  SELECT id FROM shipping_providers WHERE name='UT-SP-1' LIMIT 1
),

-- 2) scheme（挂在 provider 下）
sch AS (
  INSERT INTO shipping_provider_pricing_schemes (shipping_provider_id, name, active)
  SELECT id, 'UT-SCHEME-1', TRUE FROM sp2 LIMIT 1
  ON CONFLICT DO NOTHING
  RETURNING id
),
sch2 AS (
  SELECT id FROM sch
  UNION ALL
  SELECT s.id FROM shipping_provider_pricing_schemes s
   JOIN sp2 ON s.shipping_provider_id = sp2.id
  WHERE s.name='UT-SCHEME-1'
  LIMIT 1
),

-- 3) zone（挂在 scheme 下）
zn AS (
  INSERT INTO shipping_provider_zones (scheme_id, name, active)
  SELECT id, 'UT-ZONE-1', TRUE FROM sch2 LIMIT 1
  ON CONFLICT ON CONSTRAINT uq_sp_zones_scheme_name DO NOTHING
  RETURNING id
),
zn2 AS (
  SELECT id FROM zn
  UNION ALL
  SELECT z.id FROM shipping_provider_zones z
   JOIN sch2 ON z.scheme_id = sch2.id
  WHERE z.name='UT-ZONE-1'
  LIMIT 1
)

-- 4) brackets（挂在 zone 下，至少 2 条）
INSERT INTO shipping_provider_zone_brackets (zone_id, min_kg, max_kg, pricing_mode, flat_amount, active)
SELECT
  zn2.id,
  x.min_kg,
  x.max_kg,
  'flat',
  x.flat_amount,
  TRUE
FROM zn2
JOIN (
  VALUES
    (0.000::numeric(10,3), 1.000::numeric(10,3), 12.00::numeric(12,2)),
    (1.000::numeric(10,3), 2.000::numeric(10,3), 18.00::numeric(12,2))
) AS x(min_kg, max_kg, flat_amount)
ON TRUE
ON CONFLICT DO NOTHING;
