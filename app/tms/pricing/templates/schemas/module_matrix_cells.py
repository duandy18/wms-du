from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class ModuleMatrixCellOut(BaseModel):
    id: int
    group_id: int
    module_range_id: int
    pricing_mode: str
    flat_amount: Optional[Decimal] = None
    base_amount: Optional[Decimal] = None
    rate_per_kg: Optional[Decimal] = None
    base_kg: Optional[Decimal] = None
    active: bool


class ModuleMatrixCellsOut(BaseModel):
    ok: bool = True
    cells: list[ModuleMatrixCellOut]


class ModuleMatrixCellWriteIn(BaseModel):
    group_id: int = Field(..., ge=1)
    module_range_id: int = Field(..., ge=1)
    pricing_mode: str = Field(..., min_length=1, max_length=32)
    flat_amount: Optional[Decimal] = None
    base_amount: Optional[Decimal] = None
    rate_per_kg: Optional[Decimal] = None
    base_kg: Optional[Decimal] = None
    active: bool = True


class ModuleMatrixCellsPutIn(BaseModel):
    cells: list[ModuleMatrixCellWriteIn] = Field(default_factory=list)
