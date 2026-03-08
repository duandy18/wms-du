# app/api/routers/shipping_provider_pricing_schemes/schemas/module_ranges.py
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------
# Out Models
# ---------------------------------------------

class ModuleRangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    module_id: int
    module_code: str

    min_kg: Decimal
    max_kg: Optional[Decimal] = None

    sort_order: int
    label: str


class ModuleRangesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool = True
    module_code: str
    ranges: List[ModuleRangeOut] = Field(default_factory=list)


# ---------------------------------------------
# PUT Input
# ---------------------------------------------

class ModuleRangePutItemIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    min_kg: Decimal = Field(..., ge=0)
    max_kg: Optional[Decimal] = Field(None, ge=0)
    sort_order: Optional[int] = Field(None, ge=0)

    @model_validator(mode="after")
    def _validate_range(self):
        if self.max_kg is not None:
            if self.max_kg == Decimal("0"):
                raise ValueError("max_kg cannot be 0; use null to represent infinity")
            if self.max_kg <= self.min_kg:
                raise ValueError("max_kg must be > min_kg")
        return self


class ModuleRangesPutIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ranges: List[ModuleRangePutItemIn] = Field(default_factory=list, min_length=1)
