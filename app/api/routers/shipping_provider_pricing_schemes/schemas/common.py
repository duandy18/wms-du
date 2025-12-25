# app/api/routers/shipping_provider_pricing_schemes/schemas/common.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WeightSegmentIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # 前端用 string；后端会做强校验并规范化
    min: str = Field(..., min_length=1, max_length=32)
    max: str = Field(default="", max_length=32)  # 空 = ∞


class ZoneMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    zone_id: int
    level: str
    value: str
