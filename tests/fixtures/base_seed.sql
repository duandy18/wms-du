-- tests/fixtures/base_seed.sql
-- 说明：
-- - 测试基线主数据（items + item_barcodes）与最小库存事实（batches + stocks）
-- - 被 tests/conftest.py 在每个 test function 的 TRUNCATE 后执行
-- - 目标：让测试数据“可重复、可解释、可维护”，避免把种子硬编码在 conftest.py

-- ===== warehouses =====
INSERT INTO warehouses (id, name)
VALUES (1, 'WH-1');

-- ===== items =====
-- 目前仅使用 head schema 中最低要求字段：id/sku/name/qty_available
-- 如果以后 items 强制新增非空列（无默认），只需要改这里，不需要改 conftest.py
INSERT INTO items (id, sku, name, qty_available)
VALUES
  (1,    'SKU-0001', 'UT-ITEM-1',         0),
  (3001, 'SKU-3001', 'SOFT-RESERVE-1',    0),
  (3002, 'SKU-3002', 'SOFT-RESERVE-2',    0),
  (3003, 'SKU-3003', 'SOFT-RESERVE-BASE', 0),
  (4001, 'SKU-4001', 'OUTBOUND-MERGE',    0);

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
INSERT INTO batches (item_id, warehouse_id, batch_code, expiry_date)
VALUES
  (1,    1, 'NEAR',      CURRENT_DATE + INTERVAL '10 day'),
  (3001, 1, 'B-CONC-1',  CURRENT_DATE + INTERVAL '7 day'),
  (3002, 1, 'B-OOO-1',   CURRENT_DATE + INTERVAL '7 day'),
  (3003, 1, 'NEAR',      CURRENT_DATE + INTERVAL '5 day'),
  (4001, 1, 'B-MERGE-1', CURRENT_DATE + INTERVAL '10 day');

-- ===== stocks =====
INSERT INTO stocks (item_id, warehouse_id, batch_code, qty)
VALUES
  (1,    1, 'NEAR',      10),
  (3001, 1, 'B-CONC-1',   3),
  (3002, 1, 'B-OOO-1',    3),
  (3003, 1, 'NEAR',      10),
  (4001, 1, 'B-MERGE-1', 10);
