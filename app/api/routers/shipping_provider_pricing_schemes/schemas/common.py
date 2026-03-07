# app/api/routers/shipping_provider_pricing_schemes/schemas/common.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WeightSegmentIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # 兼容旧导出链；当前主业务已不再使用 scheme 级 segments，
    # 但保留该 schema，避免 import 链断裂。
    min: str = Field(..., min_length=1, max_length=32)
    max: str = Field(default="", max_length=32)  # 空 = ∞


class ZoneMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    zone_id: int
    level: str
    value: str
