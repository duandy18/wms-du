-- tests/fixtures/shipping_seed.sql
-- 目标：让 pricing quote 相关测试有最小可用数据
-- 策略：
-- - 幂等：以 shipping_providers.code 作为幂等键（uq_shipping_providers_code）
-- - 最小：1 provider / 1 scheme / 1 module / 1 destination_group / 2 pricing_matrix cells
--
-- 最新合同：
-- - scheme 作用域 = warehouse × provider
-- - scheme 生命周期：status = draft / active / archived
-- - 主线计价：module + module_ranges + destination_group + pricing_matrix
-- - destination_group_members 为 province-only
-- - pricing_matrix 不再直接存 min_kg / max_kg，而是引用 module_range_id

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
  pg_get_serial_sequence('shipping_provider_pricing_scheme_modules','id'),
  COALESCE((SELECT MAX(id) FROM shipping_provider_pricing_scheme_modules), 1),
  true
);

SELECT setval(
  pg_get_serial_sequence('shipping_provider_pricing_scheme_module_ranges','id'),
  COALESCE((SELECT MAX(id) FROM shipping_provider_pricing_scheme_module_ranges), 1),
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

-- 1) provider / warehouse bind / scheme / module / ranges / group
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
  SELECT id FROM shipping_providers WHERE code = 'UT-SP-1' LIMIT 1
),
wsp AS (
  INSERT INTO warehouse_shipping_providers (
    warehouse_id,
    shipping_provider_id,
    active,
    priority,
    remark
  )
  SELECT
    wh.id,
    sp2.id,
    TRUE,
    0,
    'seed bind'
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
    currency,
    default_pricing_mode,
    status,
    billable_weight_strategy,
    volume_divisor,
    rounding_mode,
    rounding_step_kg,
    min_billable_weight_kg
  )
  SELECT
    wh.id,
    sp2.id,
    'UT-SCHEME-1',
    'CNY',
    'linear_total',
    'draft',
    'actual_only',
    NULL,
    'none',
    NULL,
    NULL
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
  WHERE s.name = 'UT-SCHEME-1'
  LIMIT 1
),
mod AS (
  INSERT INTO shipping_provider_pricing_scheme_modules (
    scheme_id,
    module_code,
    name,
    sort_order
  )
  SELECT
    sch2.id,
    'standard',
    '标准区域',
    0
  FROM sch2
  ON CONFLICT ON CONSTRAINT uq_sppsm_scheme_module_code DO NOTHING
  RETURNING id
),
mod2 AS (
  SELECT id FROM mod
  UNION ALL
  SELECT m.id
  FROM shipping_provider_pricing_scheme_modules m
  JOIN sch2 ON m.scheme_id = sch2.id
  WHERE m.module_code = 'standard'
  LIMIT 1
),
mod_other AS (
  INSERT INTO shipping_provider_pricing_scheme_modules (
    scheme_id,
    module_code,
    name,
    sort_order
  )
  SELECT
    sch2.id,
    'other',
    '其他区域',
    1
  FROM sch2
  ON CONFLICT ON CONSTRAINT uq_sppsm_scheme_module_code DO NOTHING
  RETURNING id
),
r1 AS (
  INSERT INTO shipping_provider_pricing_scheme_module_ranges (
    module_id,
    min_kg,
    max_kg,
    sort_order
  )
  SELECT
    mod2.id,
    0.000::numeric(10,3),
    1.000::numeric(10,3),
    0
  FROM mod2
  ON CONFLICT ON CONSTRAINT uq_sppsmr_module_range DO NOTHING
  RETURNING id
),
r2 AS (
  INSERT INTO shipping_provider_pricing_scheme_module_ranges (
    module_id,
    min_kg,
    max_kg,
    sort_order
  )
  SELECT
    mod2.id,
    1.000::numeric(10,3),
    2.000::numeric(10,3),
    1
  FROM mod2
  ON CONFLICT ON CONSTRAINT uq_sppsmr_module_range DO NOTHING
  RETURNING id
),
dg AS (
  INSERT INTO shipping_provider_destination_groups (
    scheme_id,
    module_id,
    name,
    sort_order,
    active
  )
  SELECT
    sch2.id,
    mod2.id,
    'UT-GROUP-1',
    0,
    TRUE
  FROM sch2, mod2
  ON CONFLICT ON CONSTRAINT uq_sp_dest_groups_module_name DO NOTHING
  RETURNING id
)
SELECT 1;

-- 2) destination_group_members（province-only）
WITH wh AS (
  SELECT id FROM warehouses ORDER BY id ASC LIMIT 1
),
sp2 AS (
  SELECT id FROM shipping_providers WHERE code = 'UT-SP-1' LIMIT 1
),
sch2 AS (
  SELECT s.id
  FROM shipping_provider_pricing_schemes s
  JOIN sp2 ON s.shipping_provider_id = sp2.id
  JOIN wh ON s.warehouse_id = wh.id
  WHERE s.name = 'UT-SCHEME-1'
  LIMIT 1
),
mod2 AS (
  SELECT m.id
  FROM shipping_provider_pricing_scheme_modules m
  JOIN sch2 ON m.scheme_id = sch2.id
  WHERE m.module_code = 'standard'
  LIMIT 1
),
dg2 AS (
  SELECT g.id
  FROM shipping_provider_destination_groups g
  JOIN sch2 ON g.scheme_id = sch2.id
  JOIN mod2 ON g.module_id = mod2.id
  WHERE g.name = 'UT-GROUP-1'
  LIMIT 1
)
INSERT INTO shipping_provider_destination_group_members (
  group_id,
  province_code,
  province_name
)
SELECT
  dg2.id,
  NULL,
  '北京市'
FROM dg2
ON CONFLICT DO NOTHING;

-- 3) pricing_matrix（cellized）
WITH wh AS (
  SELECT id FROM warehouses ORDER BY id ASC LIMIT 1
),
sp2 AS (
  SELECT id FROM shipping_providers WHERE code = 'UT-SP-1' LIMIT 1
),
sch2 AS (
  SELECT s.id
  FROM shipping_provider_pricing_schemes s
  JOIN sp2 ON s.shipping_provider_id = sp2.id
  JOIN wh ON s.warehouse_id = wh.id
  WHERE s.name = 'UT-SCHEME-1'
  LIMIT 1
),
mod2 AS (
  SELECT m.id
  FROM shipping_provider_pricing_scheme_modules m
  JOIN sch2 ON m.scheme_id = sch2.id
  WHERE m.module_code = 'standard'
  LIMIT 1
),
dg2 AS (
  SELECT g.id, g.module_id
  FROM shipping_provider_destination_groups g
  JOIN sch2 ON g.scheme_id = sch2.id
  JOIN mod2 ON g.module_id = mod2.id
  WHERE g.name = 'UT-GROUP-1'
  LIMIT 1
),
ranges AS (
  SELECT
    r.id,
    r.module_id,
    r.min_kg,
    r.max_kg
  FROM shipping_provider_pricing_scheme_module_ranges r
  JOIN mod2 ON r.module_id = mod2.id
  WHERE (r.min_kg = 0.000::numeric(10,3) AND r.max_kg = 1.000::numeric(10,3))
     OR (r.min_kg = 1.000::numeric(10,3) AND r.max_kg = 2.000::numeric(10,3))
)
INSERT INTO shipping_provider_pricing_matrix (
  group_id,
  pricing_mode,
  flat_amount,
  base_amount,
  rate_per_kg,
  base_kg,
  active,
  module_range_id,
  range_module_id
)
SELECT
  dg2.id,
  'flat',
  CASE
    WHEN ranges.min_kg = 0.000::numeric(10,3) THEN 12.00::numeric(12,2)
    WHEN ranges.min_kg = 1.000::numeric(10,3) THEN 18.00::numeric(12,2)
    ELSE NULL
  END,
  NULL,
  NULL,
  NULL,
  TRUE,
  ranges.id,
  ranges.module_id
FROM dg2
JOIN ranges ON ranges.module_id = dg2.module_id
ON CONFLICT ON CONSTRAINT uq_sppm_group_module_range DO NOTHING;
