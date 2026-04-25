# app/shipping_assist/shipment/contracts_waybill_config.py
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class WaybillConfigOut(BaseModel):
    id: int
    platform: str
    shop_id: str
    shipping_provider_id: int
    shipping_provider_name: Optional[str] = None
    customer_code: str

    sender_name: Optional[str] = Field(None, max_length=64)
    sender_mobile: Optional[str] = Field(None, max_length=32)
    sender_phone: Optional[str] = Field(None, max_length=32)
    sender_province: Optional[str] = Field(None, max_length=64)
    sender_city: Optional[str] = Field(None, max_length=64)
    sender_district: Optional[str] = Field(None, max_length=64)
    sender_address: Optional[str] = Field(None, max_length=255)

    active: bool = True


class WaybillConfigListOut(BaseModel):
    ok: bool = True
    data: List[WaybillConfigOut]


class WaybillConfigDetailOut(BaseModel):
    ok: bool = True
    data: WaybillConfigOut


class WaybillConfigCreateIn(BaseModel):
    platform: str = Field(..., min_length=1, max_length=32)
    shop_id: str = Field(..., min_length=1, max_length=64)
    shipping_provider_id: int = Field(..., ge=1)
    customer_code: str = Field(..., min_length=1, max_length=64)

    sender_name: Optional[str] = Field(None, max_length=64)
    sender_mobile: Optional[str] = Field(None, max_length=32)
    sender_phone: Optional[str] = Field(None, max_length=32)
    sender_province: Optional[str] = Field(None, max_length=64)
    sender_city: Optional[str] = Field(None, max_length=64)
    sender_district: Optional[str] = Field(None, max_length=64)
    sender_address: Optional[str] = Field(None, max_length=255)

    active: bool = True


class WaybillConfigCreateOut(BaseModel):
    ok: bool = True
    data: WaybillConfigOut


class WaybillConfigUpdateIn(BaseModel):
    platform: Optional[str] = Field(None, min_length=1, max_length=32)
    shop_id: Optional[str] = Field(None, min_length=1, max_length=64)
    shipping_provider_id: Optional[int] = Field(None, ge=1)
    customer_code: Optional[str] = Field(None, min_length=1, max_length=64)

    sender_name: Optional[str] = Field(None, max_length=64)
    sender_mobile: Optional[str] = Field(None, max_length=32)
    sender_phone: Optional[str] = Field(None, max_length=32)
    sender_province: Optional[str] = Field(None, max_length=64)
    sender_city: Optional[str] = Field(None, max_length=64)
    sender_district: Optional[str] = Field(None, max_length=64)
    sender_address: Optional[str] = Field(None, max_length=255)

    active: Optional[bool] = None


class WaybillConfigUpdateOut(BaseModel):
    ok: bool = True
    data: WaybillConfigOut
