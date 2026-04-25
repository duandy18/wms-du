-- tests/fixtures/base_seed.sql
-- Lot-World baseline (v2)
-- - supplier lots keyed by lot_code_key
-- - internal lots are singleton per (warehouse_id,item_id)
--
-- Phase M-5 收口约定（工程级）：
-- ✅ base_seed.sql 只负责“主数据种子”（master data）
-- ❌ 禁止在 baseline 中写入任何库存事实：
--    - lots
--    - stocks_lot
--    - stock_ledger
--    - stock_snapshots
--
-- 库存/lot 事实必须在 tests 中显式通过统一入口构造：
--   - ensure_lot_full / ensure_internal_lot_singleton
--   - adjust_lot_impl / lot-only stock write primitives
--   - tests/helpers/inventory.py: seed_supplier_lot_slot 等
--
-- Pricing Phase-3：
-- - template 生命周期改为 draft / archived
-- - 计费重量规则改为结构化字段
-- - 运价主线改为 template + ranges + destination_groups + pricing_matrix
--
-- Pricing Phase-surcharge-config：
-- - surcharge 主线已切到 config + cities 子表
-- - base_seed 不再写 shipping_provider_surcharges 旧表

-- ===== warehouses =====
INSERT INTO warehouses (id, name, code)
VALUES (1, 'WH-1', 'WH-1')
ON CONFLICT (id) DO NOTHING;

-- ===== stores (TEST gate baseline) =====
INSERT INTO stores (id, platform, shop_id, name, active, route_mode)
VALUES (9001, 'PDD', 'UT-TEST-SHOP-1', 'UT-TEST-STORE-1', true, 'FALLBACK')
ON CONFLICT (id) DO NOTHING;

INSERT INTO platform_test_shops (platform, shop_id, store_id, code)
VALUES ('PDD', 'UT-TEST-SHOP-1', 9001, 'DEFAULT')
ON CONFLICT (platform, code)
DO UPDATE SET shop_id = EXCLUDED.shop_id, store_id = EXCLUDED.store_id;

-- ===== suppliers (minimal) =====
INSERT INTO suppliers (id, name, code, active)
VALUES
  (1, 'UT-SUP-1', 'UT-SUP-1', true),
  (3, 'UT-SUP-3', 'UT-SUP-3', true)
ON CONFLICT (id) DO NOTHING;

-- ===== shipping_providers (minimal) =====
INSERT INTO shipping_providers (id, name, code, active, priority, address)
VALUES
  (1, 'UT-CARRIER-1', 'UT-CAR-1', true, 100, 'UT-ADDR-1'),
  (2, 'Fake Express', 'FAKE', true, 100, 'UT-ADDR-FAKE')
ON CONFLICT (id) DO NOTHING;

-- ===== shipping pricing template baseline =====
-- template 主线：provider -> template -> ranges/groups -> matrix + surcharge_config
INSERT INTO shipping_provider_pricing_templates (
  id,
  shipping_provider_id,
  name,
  status,
  archived_at,
  validation_status,
  expected_ranges_count,
  expected_groups_count
)
VALUES (
  1,
  1,
  'UT-TEMPLATE-1',
  'draft',
  NULL,
  'passed',
  3,
  1
)
ON CONFLICT (id) DO UPDATE SET
  shipping_provider_id = EXCLUDED.shipping_provider_id,
  name = EXCLUDED.name,
  status = EXCLUDED.status,
  archived_at = EXCLUDED.archived_at,
  validation_status = EXCLUDED.validation_status,
  expected_ranges_count = EXCLUDED.expected_ranges_count,
  expected_groups_count = EXCLUDED.expected_groups_count;

-- ranges：单模板直挂
INSERT INTO shipping_provider_pricing_template_module_ranges (
  id,
  template_id,
  min_kg,
  max_kg,
  sort_order,
  default_pricing_mode
)
VALUES
  (1, 1, 0.000, 1.000, 0, 'flat'),
  (2, 1, 1.000, 2.000, 1, 'flat'),
  (3, 1, 2.000, NULL, 2, 'linear_total')
ON CONFLICT (id) DO UPDATE SET
  template_id = EXCLUDED.template_id,
  min_kg = EXCLUDED.min_kg,
  max_kg = EXCLUDED.max_kg,
  sort_order = EXCLUDED.sort_order,
  default_pricing_mode = EXCLUDED.default_pricing_mode;

-- destination groups：单模板直挂
INSERT INTO shipping_provider_pricing_template_destination_groups (
  id,
  template_id,
  name,
  active,
  sort_order
)
VALUES
  (1, 1, '华北测试组', true, 0)
ON CONFLICT (id) DO UPDATE SET
  template_id = EXCLUDED.template_id,
  name = EXCLUDED.name,
  active = EXCLUDED.active,
  sort_order = EXCLUDED.sort_order;

INSERT INTO shipping_provider_pricing_template_destination_group_members (
  id,
  group_id,
  province_code,
  province_name
)
VALUES
  (1, 1, NULL, '北京市'),
  (2, 1, NULL, '天津市'),
  (3, 1, NULL, '河北省')
ON CONFLICT (id) DO UPDATE SET
  group_id = EXCLUDED.group_id,
  province_code = EXCLUDED.province_code,
  province_name = EXCLUDED.province_name;

-- pricing matrix：单模板 cell 结构
INSERT INTO shipping_provider_pricing_template_matrix (
  id,
  group_id,
  pricing_mode,
  flat_amount,
  base_amount,
  rate_per_kg,
  base_kg,
  active,
  module_range_id
)
VALUES
  (1, 1, 'flat',         2.50, NULL, NULL, NULL, true, 1),
  (2, 1, 'flat',         3.80, NULL, NULL, NULL, true, 2),
  (3, 1, 'linear_total', NULL, 3.00, 1.50, NULL, true, 3)
ON CONFLICT (id) DO UPDATE SET
  group_id = EXCLUDED.group_id,
  pricing_mode = EXCLUDED.pricing_mode,
  flat_amount = EXCLUDED.flat_amount,
  base_amount = EXCLUDED.base_amount,
  rate_per_kg = EXCLUDED.rate_per_kg,
  base_kg = EXCLUDED.base_kg,
  active = EXCLUDED.active,
  module_range_id = EXCLUDED.module_range_id;

INSERT INTO warehouse_shipping_providers (
  warehouse_id,
  shipping_provider_id,
  active_template_id,
  active,
  priority,
  pickup_cutoff_time,
  remark
)
VALUES (1, 1, 1, true, 0, NULL, 'seed bind')
ON CONFLICT (warehouse_id, shipping_provider_id) DO UPDATE SET
  active_template_id = EXCLUDED.active_template_id,
  active = EXCLUDED.active,
  priority = EXCLUDED.priority,
  pickup_cutoff_time = EXCLUDED.pickup_cutoff_time,
  remark = EXCLUDED.remark;

-- ===== items =====
INSERT INTO items (
  id, sku, name,
  lot_source_policy, expiry_policy, derivation_allowed, uom_governance_enabled
)
VALUES
  (1,    'SKU-0001', 'UT-ITEM-1',
   'SUPPLIER_ONLY'::lot_source_policy, 'NONE'::expiry_policy, true, true),
  (3001, 'SKU-3001', 'SOFT-PICK-1',
   'SUPPLIER_ONLY'::lot_source_policy, 'NONE'::expiry_policy, true, true),
  (3002, 'SKU-3002', 'SOFT-PICK-2',
   'SUPPLIER_ONLY'::lot_source_policy, 'NONE'::expiry_policy, true, true),
  (3003, 'SKU-3003', 'SOFT-PICK-BASE',
   'SUPPLIER_ONLY'::lot_source_policy, 'NONE'::expiry_policy, true, true),
  (4001, 'SKU-4001', 'OUTBOUND-MERGE',
   'SUPPLIER_ONLY'::lot_source_policy, 'NONE'::expiry_policy, true, true),
  (4002, 'SKU-4002', 'PURCHASE-BASE-1',
   'SUPPLIER_ONLY'::lot_source_policy, 'NONE'::expiry_policy, true, true)
ON CONFLICT (id) DO NOTHING;

-- ===== item_uoms (unit truth source) =====
INSERT INTO item_uoms (
  item_id, uom, ratio_to_base, display_name,
  is_base, is_purchase_default, is_inbound_default, is_outbound_default
)
SELECT
  i.id,
  'PCS',
  1,
  'PCS',
  true,
  true,
  true,
  true
FROM items i
WHERE i.id IN (1, 3001, 3002, 3003, 4001, 4002)
ON CONFLICT ON CONSTRAINT uq_item_uoms_item_uom
DO UPDATE SET
  ratio_to_base = EXCLUDED.ratio_to_base,
  display_name = EXCLUDED.display_name,
  is_base = EXCLUDED.is_base,
  is_purchase_default = EXCLUDED.is_purchase_default,
  is_inbound_default = EXCLUDED.is_inbound_default,
  is_outbound_default = EXCLUDED.is_outbound_default;

-- ===== item_barcodes (primary; bind to base item_uom) =====
INSERT INTO item_barcodes (
  item_id,
  item_uom_id,
  barcode,
  symbology,
  active,
  is_primary,
  created_at,
  updated_at
)
SELECT
  i.id,
  u.id,
  'AUTO-BC-' || i.id::text,
  'CUSTOM',
  true,
  true,
  NOW(),
  NOW()
FROM items i
JOIN item_uoms u
  ON u.item_id = i.id
 AND u.is_base = true
WHERE NOT EXISTS (
  SELECT 1
  FROM item_barcodes b
  WHERE b.item_id = i.id
);

-- ===== inbound_receipts (compat placeholder) =====
-- 注意：当前 INTERNAL lot 的终态 identity 不应依赖 inbound_receipts。
-- 但某些历史路径/测试可能仍假设有一条 receipt seed，因此保留这条 placeholder。
-- 新任务模型下，这条 seed 只作为“手工来源的已发布任务单占位”，不再使用旧事实层列。
INSERT INTO inbound_receipts (
  id,
  warehouse_id,
  supplier_id,
  counterparty_name_snapshot,
  source_type,
  source_doc_id,
  source_doc_no_snapshot,
  receipt_no,
  status,
  remark,
  created_at,
  updated_at,
  warehouse_name_snapshot,
  created_by,
  released_at
)
VALUES
  (
    9000001,
    1,
    NULL,
    NULL,
    'MANUAL',
    NULL,
    NULL,
    'UT-INTERNAL-LOT-SEED-9000001',
    'RELEASED',
    'seed placeholder',
    now(),
    now(),
    'WH-1',
    NULL,
    now()
  )
ON CONFLICT (id) DO NOTHING;

-- ===== sequences =====
SELECT setval(
  pg_get_serial_sequence('warehouses','id'),
  COALESCE((SELECT MAX(id) FROM warehouses), 0),
  true
);

SELECT setval(
  pg_get_serial_sequence('stores','id'),
  COALESCE((SELECT MAX(id) FROM stores), 0),
  true
);

SELECT setval(
  pg_get_serial_sequence('shipping_providers','id'),
  COALESCE((SELECT MAX(id) FROM shipping_providers), 0),
  true
);

SELECT setval(
  pg_get_serial_sequence('shipping_provider_pricing_templates','id'),
  COALESCE((SELECT MAX(id) FROM shipping_provider_pricing_templates), 0),
  true
);

SELECT setval(
  pg_get_serial_sequence('shipping_provider_pricing_template_module_ranges','id'),
  COALESCE((SELECT MAX(id) FROM shipping_provider_pricing_template_module_ranges), 0),
  true
);

SELECT setval(
  pg_get_serial_sequence('shipping_provider_pricing_template_destination_groups','id'),
  COALESCE((SELECT MAX(id) FROM shipping_provider_pricing_template_destination_groups), 0),
  true
);

SELECT setval(
  pg_get_serial_sequence('shipping_provider_pricing_template_destination_group_members','id'),
  COALESCE((SELECT MAX(id) FROM shipping_provider_pricing_template_destination_group_members), 0),
  true
);

SELECT setval(
  pg_get_serial_sequence('shipping_provider_pricing_template_matrix','id'),
  COALESCE((SELECT MAX(id) FROM shipping_provider_pricing_template_matrix), 0),
  true
);

SELECT setval(
  pg_get_serial_sequence('items','id'),
  COALESCE((SELECT MAX(id) FROM items), 0),
  true
);

-- ===== supplier bindings / policies =====
UPDATE items
SET supplier_id = 1,
    enabled = true
WHERE id IN (3001, 3002, 4002);

UPDATE items
SET expiry_policy = 'REQUIRED'::expiry_policy,
    shelf_life_value = 30,
    shelf_life_unit = 'DAY',
    enabled = true,
    supplier_id = 1
WHERE id = 3001;

UPDATE items
SET supplier_id = 3,
    enabled = true
WHERE id = 1;
