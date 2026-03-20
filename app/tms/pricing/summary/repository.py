# app/tms/pricing/summary/repository.py

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .service import compute_is_template_active, compute_pricing_status


_SQL_PRICING_LIST = """
SELECT
  sp.id AS provider_id,
  sp.code AS provider_code,
  sp.name AS provider_name,
  sp.active AS provider_active,

  wsp.warehouse_id,
  w.name AS warehouse_name,

  wsp.active AS binding_active,

  wsp.active_template_id AS active_template_id,
  tpl.name AS active_template_name,
  tpl.status AS active_template_status,
  CASE
    WHEN tpl.archived_at IS NOT NULL THEN TRUE
    ELSE FALSE
  END AS template_archived

FROM shipping_providers sp

JOIN warehouse_shipping_providers wsp
  ON wsp.shipping_provider_id = sp.id

JOIN warehouses w
  ON w.id = wsp.warehouse_id

LEFT JOIN shipping_provider_pricing_templates tpl
  ON tpl.id = wsp.active_template_id

ORDER BY
  sp.priority ASC,
  sp.id ASC,
  wsp.priority ASC,
  wsp.warehouse_id ASC
"""


async def list_pricing_view(session: AsyncSession) -> list[dict[str, object]]:
    result = await session.execute(text(_SQL_PRICING_LIST))
    rows = result.mappings().all()

    out: list[dict[str, object]] = []
    for r in rows:
        row = dict(r)

        provider_active = bool(row["provider_active"])
        binding_active = bool(row["binding_active"])
        active_template_id = row.get("active_template_id")
        active_template_status = row.get("active_template_status")
        template_archived = bool(row.get("template_archived") or False)

        row["is_template_active"] = compute_is_template_active(
            active_template_id=active_template_id,
            template_status=active_template_status,
            template_archived=template_archived,
        )
        row["pricing_status"] = compute_pricing_status(
            provider_active=provider_active,
            binding_active=binding_active,
            active_template_id=active_template_id,
            template_status=active_template_status,
            template_archived=template_archived,
        )

        row.pop("template_archived", None)
        out.append(row)

    return out
