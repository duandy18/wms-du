from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class ModuleRangeOut(BaseModel):
    id: int
    template_id: int
    min_kg: Decimal
    max_kg: Optional[Decimal] = None
    sort_order: int
    default_pricing_mode: str
    label: str


class ModuleRangesOut(BaseModel):
    ok: bool = True
    ranges: list[ModuleRangeOut]


class ModuleRangeWriteIn(BaseModel):
    min_kg: Decimal = Field(..., ge=0)
    max_kg: Optional[Decimal] = Field(default=None, gt=0)
    sort_order: Optional[int] = Field(default=None, ge=0)
    default_pricing_mode: str = Field(default="flat", min_length=1, max_length=32)


class ModuleRangesPutIn(BaseModel):
    ranges: list[ModuleRangeWriteIn] = Field(default_factory=list)
