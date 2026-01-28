# app/api/routers/shipping_provider_pricing_schemes/schemas/zone.py
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import ZoneMemberOut
from .bracket import ZoneBracketOut


class ZoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scheme_id: int
    name: str
    active: bool

    # ✅ Phase X：Zone 绑定段结构模板（用于目的地分流后的段结构差异）
    # - None：沿用 scheme 的默认/生效段结构（兼容旧世界）
    # - 非 None：该 zone 使用指定模板的段结构（例如青海/广西）
    segment_template_id: Optional[int] = None

    members: List[ZoneMemberOut] = Field(default_factory=list)
    brackets: List[ZoneBracketOut] = Field(default_factory=list)


class ZoneCreateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=128)
    active: bool = True

    # ✅ 可选：创建时直接绑定模板
    segment_template_id: Optional[int] = None


class ZoneUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    active: Optional[bool] = None

    # ✅ 可选：patch 绑定/解绑模板（None 表示解绑）
    segment_template_id: Optional[int] = None


class ZoneCreateAtomicIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=128)
    active: bool = True
    provinces: List[str] = Field(default_factory=list, description="省份集合（必填，至少 1 个）")

    # ✅ 可选：原子创建时直接绑定模板
    segment_template_id: Optional[int] = None


class ZoneMemberCreateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    level: str = Field(..., min_length=1, max_length=16)  # province/city/district/text
    value: str = Field(..., min_length=1, max_length=64)


# ✅ 新增：原子替换某个 Zone 的 province members
class ZoneProvinceMembersReplaceIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provinces: List[str] = Field(default_factory=list, description="省份集合（必填，至少 1 个）")
