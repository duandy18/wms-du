# app/shipping_assist/pricing/bindings/helpers.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import text

from app.shipping_assist.pricing.bindings.contracts import (
    ShippingProviderLiteOut,
    WarehouseShippingProviderOut,
)
from app.shipping_assist.pricing.runtime_policy import compute_pricing_status


LIST_SQL = text(
    """
    SELECT
      wsp.warehouse_id,
      wsp.shipping_provider_id,
      wsp.active AS wsp_active,
      wsp.priority AS wsp_priority,
      wsp.pickup_cutoff_time,
      wsp.remark,
      wsp.active_template_id,
      wsp.effective_from,
      wsp.disabled_at,
      tpl.name AS active_template_name,
      sp.id AS provider_id,
      sp.name AS provider_name,
      sp.code AS provider_code,
      sp.active AS provider_active
    FROM warehouse_shipping_providers AS wsp
    JOIN shipping_providers AS sp
      ON sp.id = wsp.shipping_provider_id
    LEFT JOIN shipping_provider_pricing_templates AS tpl
      ON tpl.id = wsp.active_template_id
    WHERE wsp.warehouse_id = :wid
    ORDER BY wsp.priority ASC, wsp.id ASC
    """
)


def row_to_out(row: Dict[str, Any]) -> WarehouseShippingProviderOut:
    provider_active = bool(row["provider_active"])
    binding_active = bool(row["wsp_active"])
    active_template_id = row.get("active_template_id")
    effective_from = row.get("effective_from")
    now = datetime.now(timezone.utc)

    runtime_status = compute_pricing_status(
        provider_active=provider_active,
        binding_active=binding_active,
        active_template_id=active_template_id,
        effective_from=effective_from,
        now=now,
    )

    return WarehouseShippingProviderOut(
        warehouse_id=int(row["warehouse_id"]),
        shipping_provider_id=int(row["shipping_provider_id"]),
        active=binding_active,
        priority=int(row["wsp_priority"]),
        pickup_cutoff_time=row.get("pickup_cutoff_time"),
        remark=row.get("remark"),
        active_template_id=active_template_id,
        active_template_name=row.get("active_template_name"),
        effective_from=effective_from,
        disabled_at=row.get("disabled_at"),
        runtime_status=runtime_status,
        provider=ShippingProviderLiteOut(
            id=int(row["provider_id"]),
            name=str(row["provider_name"]),
            code=row.get("provider_code"),
            active=provider_active,
        ),
    )
