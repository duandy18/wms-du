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
    members: List[ZoneMemberOut] = Field(default_factory=list)
    brackets: List[ZoneBracketOut] = Field(default_factory=list)


class ZoneCreateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=128)
    active: bool = True


class ZoneUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    active: Optional[bool] = None


class ZoneCreateAtomicIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=128)
    active: bool = True
    provinces: List[str] = Field(default_factory=list, description="省份集合（必填，至少 1 个）")


class ZoneMemberCreateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    level: str = Field(..., min_length=1, max_length=16)  # province/city/district/text
    value: str = Field(..., min_length=1, max_length=64)
