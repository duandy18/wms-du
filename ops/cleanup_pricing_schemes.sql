-- ops/cleanup_pricing_schemes.sql
--
-- Pricing Schemes Cleanup Playbook
--
-- 用途：
--   清理 inactive 的“空壳 / 测试 / 复制”运价方案（pricing schemes），
--   避免数据库与 UI 噪声膨胀。
--
-- 设计原则：
--   1) 只清理 inactive=false 的方案
--   2) 永远先查引用，再删除
--   3) 分层删除（子表 -> 主表）
--   4) 默认 dry-run，执行需显式切换
--
-- 使用方式：
--   psql "$DEV_DB_DSN" -f ops/cleanup_pricing_schemes.sql
--
-- =========================================================
-- 配置区（唯一需要你手动确认的地方）
-- =========================================================

-- 是否执行真正删除：
--   false = dry-run（只统计）
--   true  = execute（真实删除）
\set EXECUTE false

-- 每批次最大处理数量（防止误操作）
\set BATCH_LIMIT 1000

-- =========================================================
-- 0. 总览：当前 pricing schemes 数量
-- =========================================================

select
  count(*)                                  as total,
  count(*) filter (where active=true)       as active_n,
  count(*) filter (where active=false)      as inactive_n
from shipping_provider_pricing_schemes;

-- =========================================================
-- 1. 识别【真空壳 scheme】
--    条件：inactive 且没有任何子表引用
-- =========================================================

with shell_schemes as (
  select s.id, s.name
  from shipping_provider_pricing_schemes s
  where s.active=false
    and not exists (select 1 from shipping_provider_zones z where z.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_pricing_scheme_segment_templates t where t.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_surcharges su where su.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_pricing_scheme_segments seg where seg.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_pricing_scheme_warehouses wh where wh.scheme_id=s.id)
)
select
  count(*) as shell_scheme_n
from shell_schemes;

-- 预览样例
select * from (
  select s.id, s.name
  from shipping_provider_pricing_schemes s
  where s.active=false
    and not exists (select 1 from shipping_provider_zones z where z.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_pricing_scheme_segment_templates t where t.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_surcharges su where su.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_pricing_scheme_segments seg where seg.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_pricing_scheme_warehouses wh where wh.scheme_id=s.id)
  order by s.id desc
  limit 20
) t;

-- =========================================================
-- 2. 执行删除【真空壳 scheme】
-- =========================================================

\if :EXECUTE
begin;

with target as (
  select s.id
  from shipping_provider_pricing_schemes s
  where s.active=false
    and not exists (select 1 from shipping_provider_zones z where z.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_pricing_scheme_segment_templates t where t.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_surcharges su where su.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_pricing_scheme_segments seg where seg.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_pricing_scheme_warehouses wh where wh.scheme_id=s.id)
  order by s.id desc
  limit :BATCH_LIMIT
)
delete from shipping_provider_pricing_schemes s
using target
where s.id = target.id;

commit;
\else
-- dry-run：不执行删除
\echo 'DRY-RUN: shell schemes not deleted'
\endif

-- =========================================================
-- 3. 识别【仅剩 surcharge 的空壳 scheme】
-- =========================================================

with surcharge_only as (
  select s.id, s.name,
         (select count(*) from shipping_provider_surcharges su where su.scheme_id=s.id) as surcharge_n
  from shipping_provider_pricing_schemes s
  where s.active=false
    and not exists (select 1 from shipping_provider_zones z where z.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_pricing_scheme_segment_templates t where t.scheme_id=s.id)
    and exists (select 1 from shipping_provider_surcharges su where su.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_pricing_scheme_segments seg where seg.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_pricing_scheme_warehouses wh where wh.scheme_id=s.id)
)
select
  count(*) as surcharge_only_scheme_n
from surcharge_only;

-- 预览样例
select * from (
  select s.id, s.name
  from shipping_provider_pricing_schemes s
  where s.active=false
    and not exists (select 1 from shipping_provider_zones z where z.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_pricing_scheme_segment_templates t where t.scheme_id=s.id)
    and exists (select 1 from shipping_provider_surcharges su where su.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_pricing_scheme_segments seg where seg.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_pricing_scheme_warehouses wh where wh.scheme_id=s.id)
  order by s.id desc
  limit 20
) t;

-- =========================================================
-- 4. 执行删除【仅 surcharge 的空壳 scheme】
--    顺序：surcharges -> schemes
-- =========================================================

\if :EXECUTE
begin;

with target as (
  select s.id
  from shipping_provider_pricing_schemes s
  where s.active=false
    and not exists (select 1 from shipping_provider_zones z where z.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_pricing_scheme_segment_templates t where t.scheme_id=s.id)
    and exists (select 1 from shipping_provider_surcharges su where su.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_pricing_scheme_segments seg where seg.scheme_id=s.id)
    and not exists (select 1 from shipping_provider_pricing_scheme_warehouses wh where wh.scheme_id=s.id)
  order by s.id desc
  limit :BATCH_LIMIT
)
delete from shipping_provider_surcharges su
using target
where su.scheme_id = target.id;

delete from shipping_provider_pricing_schemes s
using target
where s.id = target.id
  and s.active=false;

commit;
\else
\echo 'DRY-RUN: surcharge-only schemes not deleted'
\endif

-- =========================================================
-- 5. 收尾校验
-- =========================================================

select
  count(*)                                  as total,
  count(*) filter (where active=true)       as active_n,
  count(*) filter (where active=false)      as inactive_n
from shipping_provider_pricing_schemes;
