# app/api/routers/warehouses_shipping_providers_schemas.py
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ShippingProviderLiteOut(BaseModel):
    id: int
    name: str
    code: Optional[str] = None
    active: bool = True


class WarehouseShippingProviderOut(BaseModel):
    warehouse_id: int
    shipping_provider_id: int
    active: bool = True
    priority: int = 0
    pickup_cutoff_time: Optional[str] = None
    remark: Optional[str] = None
    provider: ShippingProviderLiteOut


class WarehouseShippingProviderListOut(BaseModel):
    ok: bool = True
    data: List[WarehouseShippingProviderOut]


class WarehouseShippingProviderBindIn(BaseModel):
    shipping_provider_id: int = Field(..., ge=1)
    active: bool = True
    priority: int = Field(default=0, ge=0)
    pickup_cutoff_time: Optional[str] = Field(
        default=None,
        description="可选：揽收截止时间（HH:MM），仅作运维字段，不参与算价。",
        max_length=5,
    )
    remark: Optional[str] = Field(default=None, max_length=255)


class WarehouseShippingProviderBindOut(BaseModel):
    ok: bool = True
    data: WarehouseShippingProviderOut


class WarehouseShippingProviderUpdateIn(BaseModel):
    active: Optional[bool] = None
    priority: Optional[int] = Field(default=None, ge=0)
    pickup_cutoff_time: Optional[str] = Field(default=None, max_length=5)
    remark: Optional[str] = Field(default=None, max_length=255)


class WarehouseShippingProviderUpdateOut(BaseModel):
    ok: bool = True
    data: WarehouseShippingProviderOut


class WarehouseShippingProviderDeleteOut(BaseModel):
    ok: bool = True
    data: dict
