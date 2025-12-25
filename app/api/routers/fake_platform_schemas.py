# app/api/routers/fake_platform_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, constr

PlatformStr = constr(min_length=1, max_length=32)


class FakeOrderStatusIn(BaseModel):
    platform: PlatformStr = Field(..., description="平台标识，例如 PDD / JD")
    shop_id: str = Field(..., min_length=1, description="店铺 ID")
    ext_order_no: str = Field(..., min_length=1, description="平台订单号 / 外部订单号")

    platform_status: str = Field(
        ...,
        description="平台订单状态（原始文案/状态码），以后会映射为内部 DELIVERED / RETURNED / LOST 等",
    )
    delivered_at: Optional[datetime] = Field(
        None,
        description="（可选）平台侧签收时间；提供时会用于 shipping_records.delivery_time",
    )

    extras: Dict[str, Any] = Field(
        default_factory=dict,
        description="（可选）附加字段，将原样写入 payload，例如 order_status_desc / refund_status 等",
    )


class FakeOrderStatusOut(BaseModel):
    ok: bool = True
    id: int
    platform: str
    shop_id: str
    ext_order_no: str
    platform_status: str
    dedup_key: Optional[str] = None
    occurred_at: datetime


class PlatformEventRow(BaseModel):
    id: int
    platform: str
    shop_id: str
    event_type: str
    status: str
    dedup_key: Optional[str] = None
    occurred_at: datetime
    payload: Dict[str, Any]


class PlatformEventListOut(BaseModel):
    ok: bool = True
    rows: List[PlatformEventRow]
