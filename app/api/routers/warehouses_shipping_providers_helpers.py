# app/api/routers/warehouses_shipping_providers_helpers.py
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import text

from app.api.routers.warehouses_shipping_providers_schemas import (
    ShippingProviderLiteOut,
    WarehouseShippingProviderOut,
)


LIST_SQL = text(
    """
    SELECT
      wsp.warehouse_id,
      wsp.shipping_provider_id,
      wsp.active AS wsp_active,
      wsp.priority AS wsp_priority,
      wsp.pickup_cutoff_time,
      wsp.remark,
      sp.id AS provider_id,
      sp.name AS provider_name,
      sp.code AS provider_code,
      sp.active AS provider_active
    FROM warehouse_shipping_providers AS wsp
    JOIN shipping_providers AS sp
      ON sp.id = wsp.shipping_provider_id
    WHERE wsp.warehouse_id = :wid
    ORDER BY wsp.priority ASC, wsp.id ASC
    """
)


def row_to_out(row: Dict[str, Any]) -> WarehouseShippingProviderOut:
    return WarehouseShippingProviderOut(
        warehouse_id=int(row["warehouse_id"]),
        shipping_provider_id=int(row["shipping_provider_id"]),
        active=bool(row["wsp_active"]),
        priority=int(row["wsp_priority"]),
        pickup_cutoff_time=row.get("pickup_cutoff_time"),
        remark=row.get("remark"),
        provider=ShippingProviderLiteOut(
            id=int(row["provider_id"]),
            name=str(row["provider_name"]),
            code=row.get("provider_code"),
            active=bool(row["provider_active"]),
        ),
    )
