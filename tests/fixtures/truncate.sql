-- tests/fixtures/truncate.sql
-- 说明：
-- - 每个 test function 开始前清库
-- - 目标：可重复、无脏数据累积
-- - 注意：这里会清掉主数据（items/warehouses）与运费域（shipping_*）以及库存/台账事实

TRUNCATE TABLE
  -- orders / order_items
  order_items,
  orders,

  -- stock / ledger / snapshots
  stock_ledger,
  stock_snapshots,
  stocks,
  batches,

  -- outbound commits
  outbound_commits,

  -- reservations
  reservation_allocations,
  reservation_lines,
  reservations,

  -- channel inventory / store_items
  channel_inventory,
  store_items,

  -- errors
  event_error_log,

  -- ===== shipping domain（避免每用例累积脏数据）=====
  shipping_provider_zone_brackets,
  shipping_provider_zone_members,
  shipping_provider_zones,
  shipping_provider_pricing_schemes,
  shipping_provider_surcharges,
  shipping_provider_contacts,
  shipping_provider_pricing_scheme_segments,
  shipping_provider_pricing_scheme_segment_templates,
  shipping_provider_pricing_scheme_segment_template_items,
  shipping_providers,
  shipping_records,

  -- master data
  warehouses,
  items
RESTART IDENTITY CASCADE;
