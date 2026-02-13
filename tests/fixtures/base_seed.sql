-- tests/fixtures/base_seed.sql
-- 说明：
-- - 测试基线主数据（items + item_barcodes）与最小库存事实（batches + stocks）
-- - 被 tests/conftest.py 在每个 test function 的 TRUNCATE 后执行
-- - 目标：让测试数据“可重复、可解释、可维护”，避免把种子硬编码在 conftest.py

-- ===== warehouses =====
INSERT INTO warehouses (id, name)
VALUES (1, 'WH-1');

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
-- 目前仅使用 head schema 中最低要求字段：id/sku/name/qty_available
-- 如果以后 items 强制新增非空列（无默认），只需要改这里，不需要改 conftest.py
INSERT INTO items (id, sku, name, qty_available)
VALUES
  (1,    'SKU-0001', 'UT-ITEM-1',         0),
  (3001, 'SKU-3001', 'SOFT-RESERVE-1',    0),
  (3002, 'SKU-3002', 'SOFT-RESERVE-2',    0),
  (3003, 'SKU-3003', 'SOFT-RESERVE-BASE', 0),
  (4001, 'SKU-4001', 'OUTBOUND-MERGE',    0),
  (4002, 'SKU-4002', 'PURCHASE-BASE-1',   0);

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
-- 修正 warehouses/items 的序列（serial/identity 时生效）
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

-- ===== batches =====
-- 注意：
-- - batches 用于“批次受控商品”的主档；非批次商品不应强行塞假批次（例如 NEAR）
INSERT INTO batches (item_id, warehouse_id, batch_code, expiry_date)
VALUES
  (3001, 1, 'B-CONC-1',  CURRENT_DATE + INTERVAL '7 day'),
  (3002, 1, 'B-OOO-1',   CURRENT_DATE + INTERVAL '7 day'),
  (4001, 1, 'B-MERGE-1', CURRENT_DATE + INTERVAL '10 day'),
  (4002, 1, 'B-PO-1',    CURRENT_DATE + INTERVAL '20 day');

-- ===== stocks =====
-- 重要：
-- - 单宇宙回归后，stocks 表不再含 scope 列
-- - 非批次商品走 NULL 槽位（与 StockService.adjust 的护栏口径一致）
INSERT INTO stocks (item_id, warehouse_id, batch_code, qty)
VALUES
  (1,    1, NULL,        10),
  (3001, 1, 'B-CONC-1',   3),
  (3002, 1, 'B-OOO-1',    3),
  (3003, 1, NULL,        10),
  (4001, 1, 'B-MERGE-1', 10),
  (4002, 1, 'B-PO-1',     0);

-- =========================
-- ✅ 采购入库测试基线：供应商-商品绑定（合同化）
-- 说明：
-- - items 表当前 insert 仅覆盖最小字段；这里用 UPDATE 给出采购所需事实字段
-- - 目标：
--   * supplier_id=1：至少 2 个可采购商品（3001/3002/4002）
--   * 其中 3001：has_shelf_life=true（用于补录/日期强约束测试）
--   * supplier_id=3：至少 1 个商品（item_id=1，错配断言用）
-- =========================

-- 供应商 1：绑定采购基线商品（用于采购创建/入库链路）
UPDATE items
SET supplier_id = 1,
    enabled = true
WHERE id IN (3001, 3002, 4002);

-- 至少一个商品开启有效期管理（用于“必须补录日期/批次”的入库测试）
UPDATE items
SET has_shelf_life = true,
    enabled = true,
    supplier_id = 1
WHERE id = 3001;

-- 供应商 3：用于错配断言（PO supplier_id=1 选 item_id=1 必须失败）
UPDATE items
SET supplier_id = 3,
    enabled = true
WHERE id = 1;
