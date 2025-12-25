# app/api/routers/shipping_records_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ShippingRecordOut(BaseModel):
    id: int
    order_ref: str
    platform: str
    shop_id: str
    warehouse_id: Optional[int] = Field(None)

    carrier_code: Optional[str] = None
    carrier_name: Optional[str] = None
    tracking_no: Optional[str] = None

    trace_id: Optional[str] = None

    weight_kg: Optional[float] = None
    gross_weight_kg: Optional[float] = None
    packaging_weight_kg: Optional[float] = None

    cost_estimated: Optional[float] = None
    cost_real: Optional[float] = None

    delivery_time: Optional[datetime] = None
    status: Optional[str] = None

    error_code: Optional[str] = None
    error_message: Optional[str] = None

    meta: Optional[dict] = None
    created_at: datetime


class ShippingStatusUpdateIn(BaseModel):
    status: Literal["IN_TRANSIT", "DELIVERED", "LOST", "RETURNED"] = Field(
        ...,
        description="发货状态：IN_TRANSIT / DELIVERED / LOST / RETURNED",
    )
    delivery_time: Optional[datetime] = Field(
        None,
        description="状态为 DELIVERED 时，如未提供则默认使用当前时间",
    )
    error_code: Optional[str] = Field(None, description="错误码（LOST/RETURNED 时可选）")
    error_message: Optional[str] = Field(None, description="错误说明（LOST/RETURNED 时可选）")
    meta: Optional[dict] = Field(
        None,
        description="附加 meta，将 merge 进原 meta（不会丢弃原有字段）",
    )


class ShippingStatusUpdateOut(BaseModel):
    ok: bool = True
    id: int
    status: str
    delivery_time: Optional[datetime] = None
