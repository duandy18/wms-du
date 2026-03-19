# app/tms/pricing/repository.py
# 分拆说明：
# - 本文件承载 TMS / Pricing（运价管理页）聚合查询；
# - 聚合三张表：
#   shipping_providers
#   warehouse_shipping_providers
#   shipping_provider_pricing_schemes
# - 输出运营视角：网点 × 仓库 当前运价状态。

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_SQL_PRICING_LIST = """
WITH active_scheme_ranked AS (
  SELECT
    sch.id,
    sch.shipping_provider_id,
    sch.warehouse_id,
    sch.name,
    sch.status,
    sch.updated_at,
    sch.created_at,
    ROW_NUMBER() OVER (
      PARTITION BY sch.shipping_provider_id, sch.warehouse_id
      ORDER BY sch.updated_at DESC, sch.id DESC
    ) AS rn
  FROM shipping_provider_pricing_schemes sch
  WHERE sch.status = 'active'
)

SELECT
  sp.id AS provider_id,
  sp.code AS provider_code,
  sp.name AS provider_name,
  sp.active AS provider_active,

  wsp.warehouse_id,
  w.name AS warehouse_name,

  wsp.active AS binding_active,

  sch.id AS active_scheme_id,
  sch.name AS active_scheme_name,
  sch.status AS active_scheme_status,

  CASE
    WHEN sp.active IS NOT TRUE THEN 'provider_disabled'
    WHEN wsp.active IS NOT TRUE THEN 'binding_disabled'
    WHEN sch.id IS NULL THEN 'no_active_scheme'
    ELSE 'ready'
  END AS pricing_status

FROM shipping_providers sp

JOIN warehouse_shipping_providers wsp
  ON wsp.shipping_provider_id = sp.id

JOIN warehouses w
  ON w.id = wsp.warehouse_id

LEFT JOIN active_scheme_ranked sch
  ON sch.shipping_provider_id = sp.id
 AND sch.warehouse_id = wsp.warehouse_id
 AND sch.rn = 1

ORDER BY
  sp.priority ASC,
  sp.id ASC,
  wsp.priority ASC,
  wsp.warehouse_id ASC
"""


async def list_pricing_view(session: AsyncSession) -> list[dict[str, object]]:
    result = await session.execute(text(_SQL_PRICING_LIST))
    rows = result.mappings().all()
    return [dict(r) for r in rows]
