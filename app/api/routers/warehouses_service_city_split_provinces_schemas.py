# app/api/routers/warehouses_service_city_split_provinces_schemas.py
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class WarehouseServiceCitySplitProvincesOut(BaseModel):
    provinces: List[str] = Field(default_factory=list)


class WarehouseServiceCitySplitProvincesPutIn(BaseModel):
    provinces: List[str] = Field(default_factory=list)
