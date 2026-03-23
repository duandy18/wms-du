# app/tms/pricing/summary/repository.py

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .service import compute_pricing_status


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

  wsp.effective_from AS effective_from,
  wsp.disabled_at AS disabled_at

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

    now = datetime.now(timezone.utc)

    out: list[dict[str, object]] = []
    for r in rows:
        row = dict(r)

        provider_active = bool(row["provider_active"])
        binding_active = bool(row["binding_active"])
        active_template_id = row.get("active_template_id")
        effective_from = row.get("effective_from")

        row["pricing_status"] = compute_pricing_status(
            provider_active=provider_active,
            binding_active=binding_active,
            active_template_id=active_template_id,
            effective_from=effective_from,
            now=now,
        )

        out.append(row)

    return out
