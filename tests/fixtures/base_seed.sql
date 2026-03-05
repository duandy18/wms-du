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
--   - adjust_lot_impl / StockService.adjust*
--   - tests/helpers/inventory.py: seed_batch_slot 等

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
INSERT INTO shipping_providers (id, name, code, external_outlet_code, active, priority, address)
VALUES
  (1, 'UT-CARRIER-1', 'UT-CAR-1', 'EXT-OUTLET-001', true, 100, 'UT-ADDR-1'),
  (2, 'Fake Express', 'FAKE', 'FAKE-OUTLET', true, 100, 'UT-ADDR-FAKE')
ON CONFLICT (id) DO NOTHING;

INSERT INTO warehouse_shipping_providers (warehouse_id, shipping_provider_id, active, priority, pickup_cutoff_time, remark)
VALUES (1, 1, true, 0, NULL, 'seed bind')
ON CONFLICT (warehouse_id, shipping_provider_id) DO UPDATE SET
  active = EXCLUDED.active,
  priority = EXCLUDED.priority,
  pickup_cutoff_time = EXCLUDED.pickup_cutoff_time,
  remark = EXCLUDED.remark;

INSERT INTO shipping_provider_pricing_schemes (id, shipping_provider_id, name, active)
VALUES (1, 1, 'UT-SCHEME-1', true)
ON CONFLICT (id) DO NOTHING;

INSERT INTO shipping_provider_pricing_scheme_warehouses (scheme_id, warehouse_id, active)
VALUES (1, 1, true)
ON CONFLICT (scheme_id, warehouse_id) DO UPDATE SET active = EXCLUDED.active;

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

-- ===== item_barcodes (primary) =====
INSERT INTO item_barcodes (item_id, barcode, kind, active, is_primary, created_at, updated_at)
SELECT
  i.id,
  'AUTO-BC-' || i.id::text,
  'CUSTOM',
  true,
  true,
  NOW(),
  NOW()
FROM items i
WHERE NOT EXISTS (SELECT 1 FROM item_barcodes b WHERE b.item_id = i.id);

-- ===== inbound_receipts (compat placeholder) =====
-- 注意：当前 INTERNAL lot 的终态 identity 不应依赖 inbound_receipts。
-- 但某些历史路径/测试可能仍假设有一条 receipt seed，因此保留这条 placeholder。
INSERT INTO inbound_receipts (
  id, warehouse_id, supplier_id, supplier_name,
  source_type, source_id, ref, trace_id,
  status, remark, occurred_at, created_at, updated_at
)
VALUES
  (
    9000001, 1, NULL, NULL,
    'SEED', NULL, 'UT-INTERNAL-LOT-SEED-9000001', NULL,
    'CONFIRMED', 'seed placeholder', now(), now(), now()
  )
ON CONFLICT (id) DO NOTHING;

-- ===== sequences =====
SELECT setval(
  pg_get_serial_sequence('warehouses','id'),
  COALESCE((SELECT MAX(id) FROM warehouses), 0),
  true
);

SELECT setval(
  pg_get_serial_sequence('items','id'),
  COALESCE((SELECT MAX(id) FROM items), 0),
  true
);

SELECT setval(
  pg_get_serial_sequence('stores','id'),
  COALESCE((SELECT MAX(id) FROM stores), 0),
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
