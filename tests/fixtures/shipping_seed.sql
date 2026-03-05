-- tests/fixtures/shipping_seed.sql
-- 目标：让 pricing quote / zone brackets unique&copy 相关测试有最小可用数据
-- 策略：
-- - 幂等：以 shipping_providers.code 作为幂等键（uq_shipping_providers_code）
-- - 最小：1 provider / 1 scheme / 1 zone / 2 brackets
--
-- ✅ 最新合同：
-- - shipping_providers 不再有 warehouse_id（网点实体，M:N 绑定在 warehouse_shipping_providers）
-- - 仓库启用关系：warehouse_shipping_providers(warehouse_id, shipping_provider_id)
-- - scheme 适用仓：shipping_provider_pricing_scheme_warehouses(scheme_id, warehouse_id)

-- 0) 关键：修正序列，避免 nextval 撞主键
-- 注意：序列最小值通常为 1，空表时不可 setval 到 0。
SELECT setval(
  pg_get_serial_sequence('shipping_providers','id'),
  COALESCE((SELECT MAX(id) FROM shipping_providers), 1),
  true
);

SELECT setval(
  pg_get_serial_sequence('shipping_provider_pricing_schemes','id'),
  COALESCE((SELECT MAX(id) FROM shipping_provider_pricing_schemes), 1),
  true
);

SELECT setval(
  pg_get_serial_sequence('shipping_provider_zones','id'),
  COALESCE((SELECT MAX(id) FROM shipping_provider_zones), 1),
  true
);

SELECT setval(
  pg_get_serial_sequence('shipping_provider_zone_brackets','id'),
  COALESCE((SELECT MAX(id) FROM shipping_provider_zone_brackets), 1),
  true
);

WITH wh AS (
  SELECT id FROM warehouses ORDER BY id ASC LIMIT 1
),

-- 1) provider（网点实体）：以 code 幂等
sp AS (
  INSERT INTO shipping_providers (name, code, active, priority, address)
  VALUES ('UT-SP-1', 'UT-SP-1', TRUE, 100, 'UT-ADDR-SP-1')
  ON CONFLICT ON CONSTRAINT uq_shipping_providers_code DO UPDATE
    SET name = EXCLUDED.name,
        active = TRUE,
        priority = EXCLUDED.priority,
        address = EXCLUDED.address
  RETURNING id
),
sp2 AS (
  SELECT id FROM sp
  UNION ALL
  SELECT id FROM shipping_providers WHERE code='UT-SP-1' LIMIT 1
),

-- 2) 绑定仓库可用网点（能力集合）
wsp AS (
  INSERT INTO warehouse_shipping_providers (warehouse_id, shipping_provider_id, active, priority, remark)
  SELECT wh.id, sp2.id, TRUE, 0, 'seed bind'
  FROM wh, sp2
  ON CONFLICT (warehouse_id, shipping_provider_id) DO UPDATE SET
    active = EXCLUDED.active,
    priority = EXCLUDED.priority,
    remark = EXCLUDED.remark
  RETURNING warehouse_id, shipping_provider_id
),

-- 3) scheme（挂在 provider 下）
sch AS (
  INSERT INTO shipping_provider_pricing_schemes (
    shipping_provider_id,
    name,
    active
  )
  SELECT
    sp2.id,
    'UT-SCHEME-1',
    TRUE
  FROM sp2
  LIMIT 1
  ON CONFLICT DO NOTHING
  RETURNING id
),
sch2 AS (
  SELECT id FROM sch
  UNION ALL
  SELECT s.id
  FROM shipping_provider_pricing_schemes s
  JOIN sp2 ON s.shipping_provider_id = sp2.id
  WHERE s.name='UT-SCHEME-1'
  LIMIT 1
),

-- 4) scheme 适用仓绑定（ship_confirm 校验会用）
spsw AS (
  INSERT INTO shipping_provider_pricing_scheme_warehouses (scheme_id, warehouse_id, active)
  SELECT sch2.id, wh.id, TRUE
  FROM sch2, wh
  ON CONFLICT (scheme_id, warehouse_id) DO UPDATE SET
    active = EXCLUDED.active
  RETURNING scheme_id, warehouse_id
),

-- 5) zone（挂在 scheme 下）
zn AS (
  INSERT INTO shipping_provider_zones (scheme_id, name, active)
  SELECT id, 'UT-ZONE-1', TRUE FROM sch2 LIMIT 1
  ON CONFLICT ON CONSTRAINT uq_sp_zones_scheme_name DO NOTHING
  RETURNING id
),
zn2 AS (
  SELECT id FROM zn
  UNION ALL
  SELECT z.id
  FROM shipping_provider_zones z
  JOIN sch2 ON z.scheme_id = sch2.id
  WHERE z.name='UT-ZONE-1'
  LIMIT 1
)

-- 6) brackets（挂在 zone 下，至少 2 条）
INSERT INTO shipping_provider_zone_brackets (
  zone_id,
  min_kg,
  max_kg,
  pricing_mode,
  flat_amount,
  active
)
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
