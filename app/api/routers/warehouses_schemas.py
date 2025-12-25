# app/api/routers/warehouses_schemas.py
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class WarehouseOut(BaseModel):
    id: int
    name: str
    code: Optional[str] = None
    active: bool = True

    address: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    area_sqm: Optional[int] = None


class WarehouseListOut(BaseModel):
    ok: bool = True
    data: List[WarehouseOut]


class WarehouseDetailOut(BaseModel):
    ok: bool = True
    data: WarehouseOut


class WarehouseCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: Optional[str] = Field(None, min_length=1, max_length=64)
    active: bool = True

    address: Optional[str] = Field(None, max_length=255)
    contact_name: Optional[str] = Field(None, max_length=100)
    contact_phone: Optional[str] = Field(None, max_length=50)
    area_sqm: Optional[int] = Field(None, ge=0)


class WarehouseCreateOut(BaseModel):
    ok: bool = True
    data: WarehouseOut


class WarehouseUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    code: Optional[str] = Field(None, min_length=1, max_length=64)
    active: Optional[bool] = None

    address: Optional[str] = Field(None, max_length=255)
    contact_name: Optional[str] = Field(None, max_length=100)
    contact_phone: Optional[str] = Field(None, max_length=50)
    area_sqm: Optional[int] = Field(None, ge=0)


class WarehouseUpdateOut(BaseModel):
    ok: bool = True
    data: WarehouseOut
