-- tests/fixtures/shipping_seed.sql
-- 目标：让 pricing quote 相关测试有最小可用数据
-- 策略：
-- - 幂等：以 shipping_providers.code 作为幂等键（uq_shipping_providers_code）
-- - 最小：1 provider / 1 scheme / 1 destination_group / 2 pricing_matrix
--
-- ✅ 最新合同（路线 A）：
-- - scheme 作用域 = warehouse × provider（shipping_provider_pricing_schemes.warehouse_id）
-- - 仓库启用关系：warehouse_shipping_providers(warehouse_id, shipping_provider_id)
-- - 主线计价：destination_group + pricing_matrix

-- 0) 修正序列
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
  pg_get_serial_sequence('shipping_provider_destination_groups','id'),
  COALESCE((SELECT MAX(id) FROM shipping_provider_destination_groups), 1),
  true
);

SELECT setval(
  pg_get_serial_sequence('shipping_provider_destination_group_members','id'),
  COALESCE((SELECT MAX(id) FROM shipping_provider_destination_group_members), 1),
  true
);

SELECT setval(
  pg_get_serial_sequence('shipping_provider_pricing_matrix','id'),
  COALESCE((SELECT MAX(id) FROM shipping_provider_pricing_matrix), 1),
  true
);

-- 1) provider / warehouse bind / scheme / destination_group
WITH wh AS (
  SELECT id FROM warehouses ORDER BY id ASC LIMIT 1
),

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

sch AS (
  INSERT INTO shipping_provider_pricing_schemes (
    warehouse_id,
    shipping_provider_id,
    name,
    active
  )
  SELECT
    wh.id,
    sp2.id,
    'UT-SCHEME-1',
    TRUE
  FROM wh, sp2
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
  JOIN wh ON s.warehouse_id = wh.id
  WHERE s.name='UT-SCHEME-1'
  LIMIT 1
),

dg AS (
  INSERT INTO shipping_provider_destination_groups (scheme_id, name, active)
  SELECT id, 'UT-GROUP-1', TRUE FROM sch2 LIMIT 1
  ON CONFLICT ON CONSTRAINT uq_sp_dest_groups_scheme_name DO NOTHING
  RETURNING id
)
SELECT 1;

-- 2) destination_group_members
WITH wh AS (
  SELECT id FROM warehouses ORDER BY id ASC LIMIT 1
),
sp2 AS (
  SELECT id FROM shipping_providers WHERE code='UT-SP-1' LIMIT 1
),
sch2 AS (
  SELECT s.id
  FROM shipping_provider_pricing_schemes s
  JOIN sp2 ON s.shipping_provider_id = sp2.id
  JOIN wh ON s.warehouse_id = wh.id
  WHERE s.name='UT-SCHEME-1'
  LIMIT 1
),
dg2 AS (
  SELECT g.id
  FROM shipping_provider_destination_groups g
  JOIN sch2 ON g.scheme_id = sch2.id
  WHERE g.name='UT-GROUP-1'
  LIMIT 1
)
INSERT INTO shipping_provider_destination_group_members (
  group_id,
  scope,
  province_name,
  city_name
)
SELECT
  dg2.id,
  'province',
  '北京市',
  NULL
FROM dg2
ON CONFLICT DO NOTHING;

-- 3) pricing_matrix
WITH wh AS (
  SELECT id FROM warehouses ORDER BY id ASC LIMIT 1
),
sp2 AS (
  SELECT id FROM shipping_providers WHERE code='UT-SP-1' LIMIT 1
),
sch2 AS (
  SELECT s.id
  FROM shipping_provider_pricing_schemes s
  JOIN sp2 ON s.shipping_provider_id = sp2.id
  JOIN wh ON s.warehouse_id = wh.id
  WHERE s.name='UT-SCHEME-1'
  LIMIT 1
),
dg2 AS (
  SELECT g.id
  FROM shipping_provider_destination_groups g
  JOIN sch2 ON g.scheme_id = sch2.id
  WHERE g.name='UT-GROUP-1'
  LIMIT 1
)
INSERT INTO shipping_provider_pricing_matrix (
  group_id,
  min_kg,
  max_kg,
  pricing_mode,
  flat_amount,
  active
)
SELECT
  dg2.id,
  x.min_kg,
  x.max_kg,
  'flat',
  x.flat_amount,
  TRUE
FROM dg2
JOIN (
  VALUES
    (0.000::numeric(10,3), 1.000::numeric(10,3), 12.00::numeric(12,2)),
    (1.000::numeric(10,3), 2.000::numeric(10,3), 18.00::numeric(12,2))
) AS x(min_kg, max_kg, flat_amount)
ON TRUE
ON CONFLICT DO NOTHING;
