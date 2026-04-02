# app/wms/warehouses/routers/warehouses_service_cities_schemas.py
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class WarehouseServiceCitiesOut(BaseModel):
    warehouse_id: int
    cities: List[str] = Field(default_factory=list)


class WarehouseServiceCitiesPutIn(BaseModel):
    cities: List[str] = Field(default_factory=list)


class WarehouseServiceCityOccupancyRow(BaseModel):
    city_code: str
    warehouse_id: int


class WarehouseServiceCityOccupancyOut(BaseModel):
    rows: List[WarehouseServiceCityOccupancyRow] = Field(default_factory=list)
