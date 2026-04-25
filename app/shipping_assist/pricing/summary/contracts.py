# app/shipping_assist/pricing/summary/contracts.py

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.shipping_assist.pricing.runtime_policy import PricingStatus


class PricingListRow(BaseModel):
    provider_id: int
    provider_code: str
    provider_name: str
    provider_active: bool

    warehouse_id: int
    warehouse_name: str

    binding_active: bool

    active_template_id: int | None = None
    active_template_name: str | None = None

    effective_from: datetime | None = None
    disabled_at: datetime | None = None

    pricing_status: PricingStatus


class PricingListResponse(BaseModel):
    ok: bool = True
    rows: list[PricingListRow]
