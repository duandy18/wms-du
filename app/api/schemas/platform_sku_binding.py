# app/api/schemas/platform_sku_binding.py
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class BindingCreateIn(BaseModel):
    platform: str = Field(..., min_length=1, max_length=50)
    shop_id: int = Field(..., ge=1)
    platform_sku_id: str = Field(..., min_length=1, max_length=200)
    fsku_id: int = Field(..., ge=1)
    reason: str | None = Field(None, max_length=200)


class BindingRow(BaseModel):
    id: int
    platform: str
    shop_id: int
    platform_sku_id: str
    fsku_id: int
    effective_from: datetime
    effective_to: datetime | None
    reason: str | None


class BindingCurrentOut(BaseModel):
    current: BindingRow


class BindingHistoryOut(BaseModel):
    items: list[BindingRow]
    total: int
    limit: int
    offset: int


class BindingMigrateIn(BaseModel):
    to_fsku_id: int = Field(..., ge=1)
    reason: str | None = Field(None, max_length=200)


class BindingMigrateOut(BaseModel):
    current: BindingRow
