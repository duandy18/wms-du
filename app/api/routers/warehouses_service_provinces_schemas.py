# app/api/routers/warehouses_service_provinces_schemas.py
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class WarehouseServiceProvincesOut(BaseModel):
    warehouse_id: int
    provinces: List[str] = Field(default_factory=list)


class WarehouseServiceProvincesPutIn(BaseModel):
    provinces: List[str] = Field(default_factory=list)


# ---------------------------
# Province Occupancy（只读）
# ---------------------------


class WarehouseServiceProvinceOccupancyRow(BaseModel):
    province_code: str
    warehouse_id: int


class WarehouseServiceProvinceOccupancyOut(BaseModel):
    rows: List[WarehouseServiceProvinceOccupancyRow] = Field(default_factory=list)
