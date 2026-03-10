-- tests/fixtures/truncate.sql
-- 说明：
-- - 每个 test function 开始前清库
-- - 目标：可重复、无脏数据累积
-- - 注意：这里会清掉主数据（items/warehouses）与运费域（shipping_*）以及库存/台账事实
--
-- Phase 4E：
-- - stocks / batches 已退场并在预演中 rename 为 *_legacy；
-- - tests 清库不再触碰 legacy 表，避免 drop 后脚本再次炸裂。
--
-- Pricing Phase-3：
-- - shipping_provider_pricing_scheme_modules 已退场；
-- - 新主线改为 ranges + pricing_matrix(cellized)。
--
-- Pricing Phase-surcharge-config：
-- - surcharge 主线已切到 surcharge_configs + surcharge_config_cities；
-- - tests 清库不再触碰 shipping_provider_surcharges 旧表。

TRUNCATE TABLE
  -- orders / order_items
  order_items,
  orders,

  -- stock / ledger / snapshots
  stock_ledger,
  stock_snapshots,

  -- outbound commits
  outbound_commits,

  -- store_items
  store_items,

  -- errors
  event_error_log,

  -- ===== shipping domain（避免每用例累积脏数据）=====
  shipping_provider_pricing_matrix,
  shipping_provider_destination_group_members,
  shipping_provider_destination_groups,
  shipping_provider_pricing_scheme_module_ranges,
  shipping_provider_surcharge_config_cities,
  shipping_provider_surcharge_configs,
  shipping_provider_pricing_schemes,
  shipping_provider_contacts,
  shipping_records,
  shipping_providers,

  -- master data
  warehouses,
  items
RESTART IDENTITY CASCADE;
