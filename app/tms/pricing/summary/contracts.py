# app/tms/pricing/summary/contracts.py

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


PricingStatus = Literal[
    "provider_disabled",
    "binding_disabled",
    "no_active_template",
    "template_not_active",
    "ready",
]


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
    active_template_status: str | None = None
    is_template_active: bool = False

    pricing_status: PricingStatus


class PricingListResponse(BaseModel):
    ok: bool = True
    rows: list[PricingListRow]
