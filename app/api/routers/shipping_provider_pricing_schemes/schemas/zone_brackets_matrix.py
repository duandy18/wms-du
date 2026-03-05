# app/api/routers/shipping_provider_pricing_schemes/schemas/zone_brackets_matrix.py
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .zone import ZoneOut


class SegmentRangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ord: int
    min_kg: Decimal
    max_kg: Optional[Decimal] = None  # null = ∞
    active: bool = True


class ZoneBracketsMatrixGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    segment_template_id: int
    template_name: str
    template_status: str
    template_is_active: bool

    segments: List[SegmentRangeOut] = Field(default_factory=list)

    # ✅ zones 仍然复用 ZoneOut（含 members/brackets/segment_template_id）
    zones: List[ZoneOut] = Field(default_factory=list)


class ZoneBracketsMatrixOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool = True
    scheme_id: int

    # ✅ 按 segment_template_id 分组后的多张“矩阵表”
    groups: List[ZoneBracketsMatrixGroupOut] = Field(default_factory=list)

    # ✅ 未绑定模板的 zones（理论上应被阻断；这里显式暴露便于 UI 提示）
    unbound_zones: List[ZoneOut] = Field(default_factory=list)
