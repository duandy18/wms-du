-- tests/fixtures/base_seed.sql
-- Lot-World baseline (v2)
-- - supplier lots keyed by lot_code_key
-- - internal lots are singleton per (warehouse_id,item_id)

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

-- ===== inbound_receipts (kept for compatibility; no longer required by INTERNAL lot) =====
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

-- ===== lots (SUPPLIER) =====
INSERT INTO lots (
  warehouse_id,
  item_id,
  lot_code_source,
  lot_code,
  lot_code_key,
  source_receipt_id,
  source_line_no,
  item_lot_source_policy_snapshot,
  item_expiry_policy_snapshot,
  item_derivation_allowed_snapshot,
  item_uom_governance_enabled_snapshot,
  item_shelf_life_value_snapshot,
  item_shelf_life_unit_snapshot
)
VALUES
  (1, 3001, 'SUPPLIER', 'B-CONC-1', lower('B-CONC-1'),
   NULL, NULL,
   'SUPPLIER_ONLY'::lot_source_policy, 'NONE'::expiry_policy, true, true,
   NULL, NULL),
  (1, 3002, 'SUPPLIER', 'B-OOO-1', lower('B-OOO-1'),
   NULL, NULL,
   'SUPPLIER_ONLY'::lot_source_policy, 'NONE'::expiry_policy, true, true,
   NULL, NULL),
  (1, 4001, 'SUPPLIER', 'B-MERGE-1', lower('B-MERGE-1'),
   NULL, NULL,
   'SUPPLIER_ONLY'::lot_source_policy, 'NONE'::expiry_policy, true, true,
   NULL, NULL),
  (1, 4002, 'SUPPLIER', 'B-PO-1', lower('B-PO-1'),
   NULL, NULL,
   'SUPPLIER_ONLY'::lot_source_policy, 'NONE'::expiry_policy, true, true,
   NULL, NULL)
ON CONFLICT (warehouse_id, item_id, lot_code_key)
WHERE lot_code IS NOT NULL
DO UPDATE SET lot_code = EXCLUDED.lot_code;

-- ===== lots (INTERNAL singleton for NONE-slot) =====
INSERT INTO lots (
  warehouse_id,
  item_id,
  lot_code_source,
  lot_code,
  lot_code_key,
  source_receipt_id,
  source_line_no,
  item_lot_source_policy_snapshot,
  item_expiry_policy_snapshot,
  item_derivation_allowed_snapshot,
  item_uom_governance_enabled_snapshot,
  item_shelf_life_value_snapshot,
  item_shelf_life_unit_snapshot
)
VALUES
  (1, 1,    'INTERNAL', NULL, NULL, NULL, NULL,
   'SUPPLIER_ONLY'::lot_source_policy, 'NONE'::expiry_policy, true, true, NULL, NULL),
  (1, 3003, 'INTERNAL', NULL, NULL, NULL, NULL,
   'SUPPLIER_ONLY'::lot_source_policy, 'NONE'::expiry_policy, true, true, NULL, NULL)
ON CONFLICT DO NOTHING;

-- ===== stocks_lot =====
-- INTERNAL: join by (wh,item) + INTERNAL + lot_code IS NULL (singleton)
INSERT INTO stocks_lot (item_id, warehouse_id, lot_id, qty)
SELECT
  x.item_id,
  x.warehouse_id,
  l.id AS lot_id,
  x.qty
FROM (
  VALUES
    (1,    1, 10),
    (3003, 1, 10)
) AS x(item_id, warehouse_id, qty)
JOIN lots l
  ON l.warehouse_id = x.warehouse_id
 AND l.item_id      = x.item_id
 AND l.lot_code_source = 'INTERNAL'
 AND l.lot_code IS NULL
ON CONFLICT ON CONSTRAINT uq_stocks_lot_item_wh_lot
DO UPDATE SET qty = EXCLUDED.qty;

-- SUPPLIER: seed by lot_code (display) is fine because we just inserted them
INSERT INTO stocks_lot (item_id, warehouse_id, lot_id, qty)
SELECT x.item_id, x.warehouse_id, l.id AS lot_id, x.qty
FROM (
  VALUES
    (3001, 1, 'B-CONC-1',  3),
    (3002, 1, 'B-OOO-1',   3),
    (4001, 1, 'B-MERGE-1', 10),
    (4002, 1, 'B-PO-1',    0)
) AS x(item_id, warehouse_id, lot_code, qty)
JOIN lots l
  ON l.warehouse_id = x.warehouse_id
 AND l.item_id      = x.item_id
 AND l.lot_code_source = 'SUPPLIER'
 AND l.lot_code     = x.lot_code
ON CONFLICT ON CONSTRAINT uq_stocks_lot_item_wh_lot
DO UPDATE SET qty = EXCLUDED.qty;

-- ===== supplier bindings =====
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
