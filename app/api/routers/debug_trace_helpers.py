# app/api/routers/debug_trace_helpers.py
from __future__ import annotations

from typing import List, Optional

from app.api.routers.debug_trace_schemas import TraceEventModel


def infer_movement_type(reason: Optional[str]) -> Optional[str]:
    if not reason:
        return None
    r = reason.upper()

    if r in {"RECEIPT", "INBOUND", "INBOUND_RECEIPT"}:
        return "INBOUND"
    if r in {"SHIP", "SHIPMENT", "OUTBOUND_SHIP", "OUTBOUND_COMMIT"}:
        return "OUTBOUND"
    if r in {"COUNT", "STOCK_COUNT", "INVENTORY_COUNT"}:
        return "COUNT"
    if r in {"ADJUSTMENT", "ADJUST", "MANUAL_ADJUST"}:
        return "ADJUST"
    if r in {"RETURN", "RMA", "INBOUND_RETURN"}:
        return "RETURN"

    return "UNKNOWN"


def filter_events_by_warehouse(
    events: List[TraceEventModel], warehouse_id: Optional[int]
) -> List[TraceEventModel]:
    if warehouse_id is None:
        return events

    filtered: List[TraceEventModel] = []
    for e in events:
        wid = e.warehouse_id
        if wid is None:
            raw = e.raw or {}
            wid = raw.get("warehouse_id") or raw.get("warehouse") or raw.get("wh_id")

        if wid is None or wid == warehouse_id:
            filtered.append(e)

    return filtered
