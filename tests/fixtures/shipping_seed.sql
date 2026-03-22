-- tests/fixtures/shipping_seed.sql
-- 目标：让 pricing quote 相关测试有最小可用数据
-- 策略：
-- - 幂等：以 shipping_providers.code 作为幂等键（uq_shipping_providers_code）
-- - 最小：1 provider / 1 template / 1 range set / 1 destination_group / 2 pricing_matrix cells
--
-- 最新合同：
-- - template 作用域 = provider；warehouse 通过 active_template_id 挂载
-- - template 生命周期：status = draft / archived
-- - validation_status：not_validated / passed / failed
-- - 主线计价：ranges + destination_group + pricing_matrix
-- - destination_group_members 为 province-only
-- - pricing_matrix 引用 module_range_id（当前表名未改），但不再有 module / range_module_id

-- 0) 修正序列
SELECT setval(
  pg_get_serial_sequence('shipping_providers','id'),
  COALESCE((SELECT MAX(id) FROM shipping_providers), 1),
  true
);

SELECT setval(
  pg_get_serial_sequence('shipping_provider_pricing_templates','id'),
  COALESCE((SELECT MAX(id) FROM shipping_provider_pricing_templates), 1),
  true
);

SELECT setval(
  pg_get_serial_sequence('shipping_provider_pricing_template_module_ranges','id'),
  COALESCE((SELECT MAX(id) FROM shipping_provider_pricing_template_module_ranges), 1),
  true
);

SELECT setval(
  pg_get_serial_sequence('shipping_provider_pricing_template_destination_groups','id'),
  COALESCE((SELECT MAX(id) FROM shipping_provider_pricing_template_destination_groups), 1),
  true
);

SELECT setval(
  pg_get_serial_sequence('shipping_provider_pricing_template_destination_group_members','id'),
  COALESCE((SELECT MAX(id) FROM shipping_provider_pricing_template_destination_group_members), 1),
  true
);

SELECT setval(
  pg_get_serial_sequence('shipping_provider_pricing_template_matrix','id'),
  COALESCE((SELECT MAX(id) FROM shipping_provider_pricing_template_matrix), 1),
  true
);

-- 1) provider / warehouse bind / template / ranges / group
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
tpl AS (
  INSERT INTO shipping_provider_pricing_templates (
    shipping_provider_id,
    name,
    status,
    archived_at,
    validation_status,
    expected_ranges_count,
    expected_groups_count
  )
  SELECT
    sp2.id,
    'UT-TEMPLATE-1',
    'draft',
    NULL,
    'passed',
    2,
    1
  FROM sp2
  LIMIT 1
  ON CONFLICT DO NOTHING
  RETURNING id
),
tpl2 AS (
  SELECT id FROM tpl
  UNION ALL
  SELECT t.id
  FROM shipping_provider_pricing_templates t
  JOIN sp2 ON t.shipping_provider_id = sp2.id
  WHERE t.name = 'UT-TEMPLATE-1'
  LIMIT 1
),
wsp AS (
  INSERT INTO warehouse_shipping_providers (
    warehouse_id,
    shipping_provider_id,
    active_template_id,
    active,
    priority,
    remark
  )
  SELECT
    wh.id,
    sp2.id,
    tpl2.id,
    TRUE,
    0,
    'seed bind'
  FROM wh, sp2, tpl2
  ON CONFLICT (warehouse_id, shipping_provider_id) DO UPDATE SET
    active_template_id = EXCLUDED.active_template_id,
    active = EXCLUDED.active,
    priority = EXCLUDED.priority,
    remark = EXCLUDED.remark
  RETURNING warehouse_id, shipping_provider_id
),
r1 AS (
  INSERT INTO shipping_provider_pricing_template_module_ranges (
    template_id,
    min_kg,
    max_kg,
    sort_order,
    default_pricing_mode
  )
  SELECT
    tpl2.id,
    0.000::numeric(10,3),
    1.000::numeric(10,3),
    0,
    'flat'
  FROM tpl2
  ON CONFLICT ON CONSTRAINT uq_spptmr_template_range DO NOTHING
  RETURNING id
),
r2 AS (
  INSERT INTO shipping_provider_pricing_template_module_ranges (
    template_id,
    min_kg,
    max_kg,
    sort_order,
    default_pricing_mode
  )
  SELECT
    tpl2.id,
    1.000::numeric(10,3),
    2.000::numeric(10,3),
    1,
    'flat'
  FROM tpl2
  ON CONFLICT ON CONSTRAINT uq_spptmr_template_range DO NOTHING
  RETURNING id
),
dg AS (
  INSERT INTO shipping_provider_pricing_template_destination_groups (
    template_id,
    name,
    sort_order,
    active
  )
  SELECT
    tpl2.id,
    'UT-GROUP-1',
    0,
    TRUE
  FROM tpl2
  ON CONFLICT ON CONSTRAINT uq_spptdg_template_sort_order DO NOTHING
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
tpl2 AS (
  SELECT t.id
  FROM shipping_provider_pricing_templates t
  JOIN sp2 ON t.shipping_provider_id = sp2.id
  WHERE t.name = 'UT-TEMPLATE-1'
  LIMIT 1
),
dg2 AS (
  SELECT g.id
  FROM shipping_provider_pricing_template_destination_groups g
  JOIN tpl2 ON g.template_id = tpl2.id
  WHERE g.sort_order = 0
  LIMIT 1
)
INSERT INTO shipping_provider_pricing_template_destination_group_members (
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
tpl2 AS (
  SELECT t.id
  FROM shipping_provider_pricing_templates t
  JOIN sp2 ON t.shipping_provider_id = sp2.id
  WHERE t.name = 'UT-TEMPLATE-1'
  LIMIT 1
),
dg2 AS (
  SELECT g.id
  FROM shipping_provider_pricing_template_destination_groups g
  JOIN tpl2 ON g.template_id = tpl2.id
  WHERE g.sort_order = 0
  LIMIT 1
),
ranges AS (
  SELECT
    r.id,
    r.min_kg,
    r.max_kg
  FROM shipping_provider_pricing_template_module_ranges r
  JOIN tpl2 ON r.template_id = tpl2.id
  WHERE (r.min_kg = 0.000::numeric(10,3) AND r.max_kg = 1.000::numeric(10,3))
     OR (r.min_kg = 1.000::numeric(10,3) AND r.max_kg = 2.000::numeric(10,3))
)
INSERT INTO shipping_provider_pricing_template_matrix (
  group_id,
  pricing_mode,
  flat_amount,
  base_amount,
  rate_per_kg,
  base_kg,
  active,
  module_range_id
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
  ranges.id
FROM dg2
CROSS JOIN ranges
ON CONFLICT ON CONSTRAINT uq_spptm_group_module_range DO NOTHING;
