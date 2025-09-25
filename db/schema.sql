-- db/schema.sql
-- WMS-DU · Minimal MVP Schema (PostgreSQL)
-- 采购 → 入库 → 库存 → 出库 的最小闭环

BEGIN;

-- ========== 1) 基础主数据 ==========
CREATE TABLE IF NOT EXISTS suppliers (
  supplier_id    BIGSERIAL PRIMARY KEY,
  supplier_code  VARCHAR(32) UNIQUE NOT NULL,
  name           TEXT NOT NULL,
  contact_name   TEXT,
  phone          TEXT,
  email          TEXT,
  tax_id         TEXT,
  status         SMALLINT NOT NULL DEFAULT 1,   -- 1启用/0停用
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
  product_id     BIGSERIAL PRIMARY KEY,
  sku            VARCHAR(64) UNIQUE NOT NULL,
  name           TEXT NOT NULL,
  spec           TEXT,
  unit           VARCHAR(16) DEFAULT 'EA',
  barcode        VARCHAR(64),
  weight_gram    INTEGER,
  volume_cc      INTEGER,
  status         SMALLINT NOT NULL DEFAULT 1,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 仓库与库位（可先：warehouse_code='MAIN' + 若干库位）
CREATE TABLE IF NOT EXISTS locations (
  location_id    BIGSERIAL PRIMARY KEY,
  warehouse_code VARCHAR(32) NOT NULL,
  location_code  VARCHAR(64) NOT NULL,
  type           VARCHAR(16) DEFAULT 'BIN',     -- BIN/DOCK/RETURN/...
  is_active      BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE (warehouse_code, location_code)
);

-- ========== 2) 采购与入库 ==========
-- 采购单（头）
CREATE TABLE IF NOT EXISTS purchase_orders (
  po_id          BIGSERIAL PRIMARY KEY,
  po_no          VARCHAR(32) UNIQUE NOT NULL,
  supplier_id    BIGINT NOT NULL REFERENCES suppliers(supplier_id),
  status         VARCHAR(16) NOT NULL DEFAULT 'CREATED', -- CREATED/APPROVED/PART_RECEIVED/CLOSED/CANCELLED
  currency       VARCHAR(8) DEFAULT 'CNY',
  expected_date  DATE,
  remark         TEXT,
  trace_id       VARCHAR(64),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 采购单（行）
CREATE TABLE IF NOT EXISTS purchase_order_items (
  poi_id         BIGSERIAL PRIMARY KEY,
  po_id          BIGINT NOT NULL REFERENCES purchase_orders(po_id) ON DELETE CASCADE,
  product_id     BIGINT NOT NULL REFERENCES products(product_id),
  qty_ordered    NUMERIC(18,3) NOT NULL,
  price_tax_incl NUMERIC(18,4),       -- 含税单价（可选）
  tax_rate       NUMERIC(6,4),
  qty_received   NUMERIC(18,3) NOT NULL DEFAULT 0,
  UNIQUE (po_id, product_id)
);

-- 入库单（头）
CREATE TABLE IF NOT EXISTS receipts (
  receipt_id     BIGSERIAL PRIMARY KEY,
  receipt_no     VARCHAR(32) UNIQUE NOT NULL,
  po_id          BIGINT REFERENCES purchase_orders(po_id),
  warehouse_code VARCHAR(32) NOT NULL,
  status         VARCHAR(16) NOT NULL DEFAULT 'CREATED', -- CREATED/CONFIRMED/CANCELLED
  received_at    TIMESTAMPTZ,
  trace_id       VARCHAR(64),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 入库单（行）
CREATE TABLE IF NOT EXISTS receipt_items (
  ri_id          BIGSERIAL PRIMARY KEY,
  receipt_id     BIGINT NOT NULL REFERENCES receipts(receipt_id) ON DELETE CASCADE,
  product_id     BIGINT NOT NULL REFERENCES products(product_id),
  location_id    BIGINT NOT NULL REFERENCES locations(location_id),
  qty_received   NUMERIC(18,3) NOT NULL,
  UNIQUE (receipt_id, product_id, location_id)
);

-- ========== 3) 出库 ==========
-- 出库单（头）
CREATE TABLE IF NOT EXISTS outbound_orders (
  out_id         BIGSERIAL PRIMARY KEY,
  out_no         VARCHAR(32) UNIQUE NOT NULL,
  warehouse_code VARCHAR(32) NOT NULL,
  reason         VARCHAR(16) NOT NULL DEFAULT 'SALE',   -- SALE/TRANSFER/ADJUST
  status         VARCHAR(16) NOT NULL DEFAULT 'CREATED',-- CREATED/PICKED/SHIPPED/CANCELLED
  trace_id       VARCHAR(64),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 出库单（行）
CREATE TABLE IF NOT EXISTS outbound_items (
  oi_id          BIGSERIAL PRIMARY KEY,
  out_id         BIGINT NOT NULL REFERENCES outbound_orders(out_id) ON DELETE CASCADE,
  product_id     BIGINT NOT NULL REFERENCES products(product_id),
  location_id    BIGINT NOT NULL REFERENCES locations(location_id),
  qty_picked     NUMERIC(18,3) NOT NULL DEFAULT 0,
  qty_shipped    NUMERIC(18,3) NOT NULL DEFAULT 0,
  UNIQUE (out_id, product_id, location_id)
);

-- ========== 4) 库存 ==========
-- 库存流水台账（事件溯源）
CREATE TABLE IF NOT EXISTS inventory_ledger (
  led_id         BIGSERIAL PRIMARY KEY,
  event_time     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  warehouse_code VARCHAR(32) NOT NULL,
  location_id    BIGINT NOT NULL REFERENCES locations(location_id),
  product_id     BIGINT NOT NULL REFERENCES products(product_id),
  qty_delta      NUMERIC(18,3) NOT NULL,  -- 入库为正，出库为负
  source_type    VARCHAR(16) NOT NULL,    -- RECEIPT/OUTBOUND/ADJUST
  source_id      BIGINT NOT NULL,         -- receipts.receipt_id / outbound_orders.out_id / ...
  trace_id       VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS idx_ledger_prod_loc_time
  ON inventory_ledger(product_id, location_id, event_time DESC);

-- 库存现势（聚合快照）
CREATE TABLE IF NOT EXISTS inventory_balance (
  product_id     BIGINT NOT NULL REFERENCES products(product_id),
  location_id    BIGINT NOT NULL REFERENCES locations(location_id),
  qty_on_hand    NUMERIC(18,3) NOT NULL DEFAULT 0,
  qty_allocated  NUMERIC(18,3) NOT NULL DEFAULT 0,
  qty_available  NUMERIC(18,3) GENERATED ALWAYS AS (qty_on_hand - qty_allocated) STORED,
  PRIMARY KEY (product_id, location_id)
);

-- ========== 5) 常用索引 ==========
CREATE INDEX IF NOT EXISTS idx_products_name ON products (name);
CREATE INDEX IF NOT EXISTS idx_locations_wh ON locations (warehouse_code);
CREATE INDEX IF NOT EXISTS idx_po_status ON purchase_orders (status);
CREATE INDEX IF NOT EXISTS idx_receipts_status ON receipts (status);
CREATE INDEX IF NOT EXISTS idx_outbound_status ON outbound_orders (status);

COMMIT;
