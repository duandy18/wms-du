# app/api/routers/shipping_provider_pricing_schemes/schemas/zone.py
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .bracket import ZoneBracketOut
from .common import ZoneMemberOut


class ZoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scheme_id: int
    name: str
    active: bool

    # ✅ 新合同（按你本次裁决）：
    # - zones 页面只负责“编辑区域（省份/启停/名称）”
    # - 重量段模板绑定统一在二维工作台完成
    # - 因此：Zone.segment_template_id 在读模型中允许为空
    segment_template_id: Optional[int] = None

    members: List[ZoneMemberOut] = Field(default_factory=list)
    brackets: List[ZoneBracketOut] = Field(default_factory=list)


class ZoneCreateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=128)
    active: bool = True

    # ✅ 创建允许不绑定（绑定由二维工作台负责）
    segment_template_id: Optional[int] = None


class ZoneUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    active: Optional[bool] = None

    # ✅ PATCH 允许：
    # - 不提供：不更新模板绑定
    # - 提供 null：清空绑定（由二维工作台重新绑定）
    # - 提供 int：更新绑定
    segment_template_id: Optional[int] = None


class ZoneCreateAtomicIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=128)
    active: bool = True
    provinces: List[str] = Field(default_factory=list, description="省份集合（必填，至少 1 个）")

    # ✅ 原子创建同样允许不绑定（绑定由二维工作台负责）
    segment_template_id: Optional[int] = None


class ZoneMemberCreateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    level: str = Field(..., min_length=1, max_length=16)  # province/city/district/text
    value: str = Field(..., min_length=1, max_length=64)


# ✅ 原子替换某个 Zone 的 province members
class ZoneProvinceMembersReplaceIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provinces: List[str] = Field(default_factory=list, description="省份集合（必填，至少 1 个）")
