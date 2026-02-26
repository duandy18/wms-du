-- tests/fixtures/base_seed.sql
-- 说明：
-- - 测试基线主数据（items + item_barcodes）与最小库存事实
-- - Phase 4E：lot-world 为真相：lots + stocks_lot 作为主事实
-- - baseline 禁止再写 legacy batches + stocks（避免双余额源 / 口径回退）

-- ===== warehouses =====
INSERT INTO warehouses (id, name)
VALUES (1, 'WH-1');

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

-- ===== items =====
-- 目前仅使用 head schema 中最低要求字段：id/sku/name
-- 如果以后 items 强制新增非空列（无默认），只需要改这里，不需要改 conftest.py
INSERT INTO items (id, sku, name)
VALUES
  (1,    'SKU-0001', 'UT-ITEM-1'),
  (3001, 'SKU-3001', 'SOFT-PICK-1'),
  (3002, 'SKU-3002', 'SOFT-PICK-2'),
  (3003, 'SKU-3003', 'SOFT-PICK-BASE'),
  (4001, 'SKU-4001', 'OUTBOUND-MERGE'),
  (4002, 'SKU-4002', 'PURCHASE-BASE-1');

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

-- ===== Phase 4D lots (SUPPLIER) =====
-- 目的：
-- - lot-world 为真相：用与 batch_code 同名的 lot_code 构造 lot
-- - SUPPLIER 约束：lot_code 必须非空，source_receipt/source_line 必须为 NULL
--
-- 注意：
-- - uq_lots_supplier_wh_item_lot_code 是 partial unique index（不是 constraint）
-- - 需要用 ON CONFLICT (cols) WHERE predicate 形式匹配
INSERT INTO lots (
  warehouse_id,
  item_id,
  lot_code_source,
  lot_code,
  production_date,
  expiry_date,
  expiry_source
)
VALUES
  (1, 3001, 'SUPPLIER', 'B-CONC-1',  CURRENT_DATE, CURRENT_DATE + INTERVAL '7 day',  'EXPLICIT'),
  (1, 3002, 'SUPPLIER', 'B-OOO-1',   CURRENT_DATE, CURRENT_DATE + INTERVAL '7 day',  'EXPLICIT'),
  (1, 4001, 'SUPPLIER', 'B-MERGE-1', CURRENT_DATE, CURRENT_DATE + INTERVAL '10 day', 'EXPLICIT'),
  (1, 4002, 'SUPPLIER', 'B-PO-1',    CURRENT_DATE, CURRENT_DATE + INTERVAL '20 day', 'EXPLICIT')
ON CONFLICT (warehouse_id, item_id, lot_code_source, lot_code)
WHERE lot_code_source = 'SUPPLIER'
DO UPDATE SET expiry_date = EXCLUDED.expiry_date;

-- ===== Phase 4D stocks_lot =====
-- 非批次商品：lot_id=NULL 槽位（lot_id_key=0）
INSERT INTO stocks_lot (item_id, warehouse_id, lot_id, qty)
VALUES
  (1,    1, NULL, 10),
  (3003, 1, NULL, 10)
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
-- 说明：
-- - items 表当前 insert 仅覆盖最小字段；这里用 UPDATE 给出采购所需事实字段
-- =========================

-- 供应商 1：绑定采购基线商品（用于采购创建/入库链路）
UPDATE items
SET supplier_id = 1,
    enabled = true
WHERE id IN (3001, 3002, 4002);

-- 至少一个商品开启有效期管理（用于“必须补录日期/批次”的入库测试）
UPDATE items
SET has_shelf_life = true,
    -- ✅ 合同收敛：has_shelf_life=true 必须同时具备 shelf_life_value/unit（满足 DB CHECK）
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
