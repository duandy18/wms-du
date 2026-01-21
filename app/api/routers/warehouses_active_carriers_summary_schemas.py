# app/api/routers/warehouses_active_carriers_summary_schemas.py
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class ActiveCarrierOut(BaseModel):
    provider_id: int
    code: Optional[str] = None
    name: str
    priority: int


class WarehouseActiveCarriersOut(BaseModel):
    warehouse_id: int
    active_carriers: List[ActiveCarrierOut]
    active_carriers_count: int


class WarehouseActiveCarriersSummaryOut(BaseModel):
    ok: bool
    data: List[WarehouseActiveCarriersOut]
