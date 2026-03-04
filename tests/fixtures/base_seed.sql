-- tests/fixtures/base_seed.sql
-- 说明：
-- - 测试基线主数据（items + item_uoms + item_barcodes）与最小库存事实
-- - Phase M-5：单位真相源唯一为 item_uoms；执行域统一 base qty 口径
-- - lot-world 为真相：lots + stocks_lot 作为主事实（stocks_lot.lot_id NOT NULL）
-- - baseline 禁止再写 legacy batches + stocks（避免双余额源 / 口径回退）

-- ===== warehouses =====
INSERT INTO warehouses (id, name, code)
VALUES (1, 'WH-1', 'WH-1')
ON CONFLICT (id) DO NOTHING;

-- ===== stores (TEST gate baseline) =====
-- 目的：
-- - order-sim 系列接口有 TEST 店铺门禁：必须命中 platform_test_shops(code='DEFAULT')
-- - contract test: tests/api/test_stores_order_sim_filled_code_options_contract.py 需要至少一个 TEST store
--
-- 约束说明：
-- - stores.store_code NOT NULL，但由触发器 trg_stores_store_code_default BEFORE INSERT 自动生成
-- - stores(platform, shop_id) UNIQUE
-- - platform_test_shops(platform, code) UNIQUE：每个平台只有一个 DEFAULT 测试集合
INSERT INTO stores (id, platform, shop_id, name, active, route_mode)
VALUES (9001, 'PDD', 'UT-TEST-SHOP-1', 'UT-TEST-STORE-1', true, 'FALLBACK')
ON CONFLICT (id) DO NOTHING;

-- 绑定 TEST 门禁：唯一真相（platform_test_shops）
INSERT INTO platform_test_shops (platform, shop_id, store_id, code)
VALUES ('PDD', 'UT-TEST-SHOP-1', 9001, 'DEFAULT')
ON CONFLICT (platform, code)
DO UPDATE SET shop_id = EXCLUDED.shop_id, store_id = EXCLUDED.store_id;

-- ===== suppliers (minimal) =====
-- 目的：
-- - items.supplier_id 有 FK 约束（fk_items_supplier），测试基线必须提供供应商主数据
-- - 仅插入采购入库测试必需的两条：id=1 / id=3
INSERT INTO suppliers (id, name, code, active)
VALUES
  (1, 'UT-SUP-1', 'UT-SUP-1', true),
  (3, 'UT-SUP-3', 'UT-SUP-3', true)
ON CONFLICT (id) DO NOTHING;

-- ===== shipping_providers (minimal) =====
-- 目的：
-- - 快递/网点主数据最小集合（供 ship_confirm / pricing 绑定使用）
-- - 注意：shipping_providers.code 为内部业务键（NOT NULL，且 DB 级不可变/规范化）
INSERT INTO shipping_providers (id, name, code, external_outlet_code, active, priority, address)
VALUES
  (1, 'UT-CARRIER-1', 'UT-CAR-1', 'EXT-OUTLET-001', true, 100, 'UT-ADDR-1'),
  (2, 'Fake Express', 'FAKE', 'FAKE-OUTLET', true, 100, 'UT-ADDR-FAKE')
ON CONFLICT (id) DO NOTHING;

-- 仓库启用网点（能力集合）
INSERT INTO warehouse_shipping_providers (warehouse_id, shipping_provider_id, active, priority, pickup_cutoff_time, remark)
VALUES (1, 1, true, 0, NULL, 'seed bind')
ON CONFLICT (warehouse_id, shipping_provider_id) DO UPDATE SET
  active = EXCLUDED.active,
  priority = EXCLUDED.priority,
  pickup_cutoff_time = EXCLUDED.pickup_cutoff_time,
  remark = EXCLUDED.remark;

-- 运价方案（最小可用：仅用于 confirm 的 scheme 绑定校验，不要求 brackets/zones）
INSERT INTO shipping_provider_pricing_schemes (id, shipping_provider_id, name, active)
VALUES (1, 1, 'UT-SCHEME-1', true)
ON CONFLICT (id) DO NOTHING;

-- 方案适用仓绑定（confirm 的 scheme_warehouses 校验依赖）
INSERT INTO shipping_provider_pricing_scheme_warehouses (scheme_id, warehouse_id, active)
VALUES (1, 1, true)
ON CONFLICT (scheme_id, warehouse_id) DO UPDATE SET active = EXCLUDED.active;

-- ===== items =====
-- Phase M-5：items.uom 已物理删除；items policy NOT NULL 且无默认，baseline 必须补齐。
-- 默认策略：
-- - lot_source_policy: SUPPLIER_ONLY
-- - expiry_policy: NONE（除非明确设为 REQUIRED）
-- - derivation_allowed: true
-- - uom_governance_enabled: true（单位治理开启，真相在 item_uoms）
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
-- Phase M-5：单位真相源唯一为 item_uoms
-- baseline 策略：每个 item 至少一条 base uom（PCS, ratio=1），并作为 purchase/inbound/outbound default。
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
-- 每个 item 生成一个主条码：AUTO-BC-{item_id}
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
WHERE NOT EXISTS (
  SELECT 1 FROM item_barcodes b WHERE b.item_id = i.id
);

-- ===== inbound_receipts (seed for INTERNAL lot FK) =====
-- lots.source_receipt_id 有 FK -> inbound_receipts.id，因此 INTERNAL lot 的 source_receipt_id 必须先存在
INSERT INTO inbound_receipts (
  id, warehouse_id, supplier_id, supplier_name,
  source_type, source_id, ref, trace_id,
  status, remark, occurred_at, created_at, updated_at
)
VALUES
  (
    9000001, 1, NULL, NULL,
    'SEED', NULL, 'UT-INTERNAL-LOT-SEED-9000001', NULL,
    'CONFIRMED', 'seed for INTERNAL lots FK', now(), now(), now()
  )
ON CONFLICT (id) DO NOTHING;

-- ===== sequences =====
-- 修正 warehouses/items/stores 的序列（serial/identity 时生效）
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
-- DB 索引：uq_lots_wh_item_lot_code UNIQUE (warehouse_id,item_id,lot_code) WHERE lot_code IS NOT NULL
INSERT INTO lots (
  warehouse_id,
  item_id,
  lot_code_source,
  lot_code,
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
  (1, 3001, 'SUPPLIER', 'B-CONC-1',
   NULL, NULL,
   'SUPPLIER_ONLY'::lot_source_policy, 'NONE'::expiry_policy, true, true,
   NULL, NULL),
  (1, 3002, 'SUPPLIER', 'B-OOO-1',
   NULL, NULL,
   'SUPPLIER_ONLY'::lot_source_policy, 'NONE'::expiry_policy, true, true,
   NULL, NULL),
  (1, 4001, 'SUPPLIER', 'B-MERGE-1',
   NULL, NULL,
   'SUPPLIER_ONLY'::lot_source_policy, 'NONE'::expiry_policy, true, true,
   NULL, NULL),
  (1, 4002, 'SUPPLIER', 'B-PO-1',
   NULL, NULL,
   'SUPPLIER_ONLY'::lot_source_policy, 'NONE'::expiry_policy, true, true,
   NULL, NULL)
ON CONFLICT (warehouse_id, item_id, lot_code)
WHERE lot_code IS NOT NULL
DO UPDATE SET lot_code = EXCLUDED.lot_code;

-- ===== lots (INTERNAL for NONE-slot) =====
-- DB 索引：uq_lots_internal_wh_item_src_receipt_line UNIQUE (warehouse_id,item_id,source_receipt_id,source_line_no) WHERE lot_code_source='INTERNAL'
INSERT INTO lots (
  warehouse_id,
  item_id,
  lot_code_source,
  lot_code,
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
  (1, 1,    'INTERNAL', NULL, 9000001, 1,
   'SUPPLIER_ONLY'::lot_source_policy, 'NONE'::expiry_policy, true, true, NULL, NULL),
  (1, 3003, 'INTERNAL', NULL, 9000001, 1,
   'SUPPLIER_ONLY'::lot_source_policy, 'NONE'::expiry_policy, true, true, NULL, NULL)
ON CONFLICT (warehouse_id, item_id, source_receipt_id, source_line_no)
WHERE lot_code_source::text = 'INTERNAL'::text
DO UPDATE SET source_line_no = EXCLUDED.source_line_no;

-- ===== stocks_lot =====
-- DB 事实：stocks_lot.lot_id NOT NULL
-- 非批次商品：INTERNAL lot 槽位（lot_code=NULL，但 lot_id 存在）
INSERT INTO stocks_lot (item_id, warehouse_id, lot_id, qty)
SELECT
  x.item_id,
  x.warehouse_id,
  l.id AS lot_id,
  x.qty
FROM (
  VALUES
    (1,    1, 9000001, 1, 10),
    (3003, 1, 9000001, 1, 10)
) AS x(item_id, warehouse_id, source_receipt_id, source_line_no, qty)
JOIN lots l
  ON l.warehouse_id = x.warehouse_id
 AND l.item_id      = x.item_id
 AND l.lot_code_source = 'INTERNAL'
 AND l.source_receipt_id = x.source_receipt_id
 AND l.source_line_no = x.source_line_no
ON CONFLICT ON CONSTRAINT uq_stocks_lot_item_wh_lot
DO UPDATE SET qty = EXCLUDED.qty;

-- 批次商品：lot_id 指向 lots（按 lot_code 精确定位）
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

-- =========================
-- ✅ 采购入库测试基线：供应商-商品绑定（合同化）
-- =========================

-- 供应商 1：绑定采购基线商品（用于采购创建/入库链路）
UPDATE items
SET supplier_id = 1,
    enabled = true
WHERE id IN (3001, 3002, 4002);

-- 至少一个商品开启有效期管理（用于“必须补录日期/批次”的入库测试）
-- Phase M-5：expiry_policy=REQUIRED 时必须具备 shelf_life_value/unit（满足 ck_items_expiry_policy_vs_shelf_life）
UPDATE items
SET expiry_policy = 'REQUIRED'::expiry_policy,
    shelf_life_value = 30,
    shelf_life_unit = 'DAY',
    enabled = true,
    supplier_id = 1
WHERE id = 3001;

-- 供应商 3：用于错配断言（PO supplier_id=1 选 item_id=1 必须失败）
UPDATE items
SET supplier_id = 3,
    enabled = true
WHERE id = 1;
