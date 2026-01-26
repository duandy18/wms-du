# app/api/routers/shipping_provider_pricing_schemes/schemas/scheme.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import WeightSegmentIn
from .surcharge import SurchargeOut
from .zone import ZoneOut


class SchemeSegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scheme_id: int
    ord: int
    min_kg: Any
    max_kg: Any = None
    active: bool = True


class SchemeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shipping_provider_id: int
    name: str
    active: bool

    # ✅ 归档：archived_at != null => 已归档（默认列表应隐藏）
    archived_at: Optional[datetime] = None

    currency: str
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None

    # ✅ 方案默认口径（方案级：一套表一个口径）
    default_pricing_mode: str

    billable_weight_rule: Optional[Dict[str, Any]] = None

    # ✅ Phase 4.3：列结构（重量分段模板）后端真相（兼容/镜像）
    segments_json: Optional[List[WeightSegmentIn]] = None
    segments_updated_at: Optional[datetime] = None

    # ✅ 新增：结构化段表输出（含 active/id）
    segments: List[SchemeSegmentOut] = Field(default_factory=list)

    zones: List[ZoneOut] = Field(default_factory=list)
    surcharges: List[SurchargeOut] = Field(default_factory=list)


class SchemeListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool = True
    data: List[SchemeOut]


class SchemeDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool = True
    data: SchemeOut


class SchemeCreateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=128)
    active: bool = True
    currency: str = Field(default="CNY", min_length=1, max_length=8)

    # ✅ 方案默认口径（默认 linear_total）
    default_pricing_mode: str = Field(default="linear_total", min_length=1, max_length=32)

    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    billable_weight_rule: Optional[Dict[str, Any]] = None

    # ✅ Phase 4.3：允许创建时直接写入列结构
    segments_json: Optional[List[WeightSegmentIn]] = None


class SchemeUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    active: Optional[bool] = None

    # ✅ 归档：设置为某个时间 => 归档；显式设为 null => 取消归档
    # - 归档时后端会强制 active=false（写路由负责）
    archived_at: Optional[datetime] = None

    currency: Optional[str] = Field(None, min_length=1, max_length=8)

    # ✅ 方案默认口径
    default_pricing_mode: Optional[str] = Field(None, min_length=1, max_length=32)

    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    billable_weight_rule: Optional[Dict[str, Any]] = None

    # ✅ Phase 4.3：列结构更新（允许显式设 null 清空）
    segments_json: Optional[List[WeightSegmentIn]] = None
