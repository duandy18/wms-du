# app/api/routers/warehouses_service_provinces_schemas.py
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class WarehouseServiceProvincesOut(BaseModel):
    warehouse_id: int
    provinces: List[str] = Field(default_factory=list)


class WarehouseServiceProvincesPutIn(BaseModel):
    provinces: List[str] = Field(default_factory=list)
