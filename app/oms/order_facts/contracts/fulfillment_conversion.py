from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FulfillmentOrderConversionIn(BaseModel):
    mirror_id: int = Field(..., ge=1)


class FulfillmentOrderConversionOut(BaseModel):
    ok: bool = True

    platform: str
    mirror_id: int
    order_id: int | None
    ref: str
    status: str

    store_id: int
    store_code: str
    ext_order_no: str

    lines_count: int
    item_lines_count: int

    fulfillment_status: str | None = None
    blocked_reasons: Any = None
    risk_flags: list[str] = Field(default_factory=list)
