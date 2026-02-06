# app/api/schemas/platform_sku_binding.py
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class BindingCreateIn(BaseModel):
    platform: str = Field(..., min_length=1, max_length=50)
    shop_id: int = Field(..., ge=1)
    platform_sku_id: str = Field(..., min_length=1, max_length=200)

    # 目标二选一：单品用 item_id；组合用 fsku_id
    item_id: int | None = Field(None, ge=1)
    fsku_id: int | None = Field(None, ge=1)

    reason: str | None = Field(None, max_length=200)

    @model_validator(mode="after")
    def _xor_target(self) -> "BindingCreateIn":
        has_item = self.item_id is not None
        has_fsku = self.fsku_id is not None
        if has_item == has_fsku:
            raise ValueError("item_id 与 fsku_id 必须二选一（且只能选一个）")
        return self


class BindingUnbindIn(BaseModel):
    platform: str = Field(..., min_length=1, max_length=50)
    shop_id: int = Field(..., ge=1)
    platform_sku_id: str = Field(..., min_length=1, max_length=200)
    reason: str | None = Field(None, max_length=200)


class BindingRow(BaseModel):
    id: int
    platform: str
    shop_id: int
    platform_sku_id: str

    item_id: int | None
    fsku_id: int | None

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
    # 迁移目标二选一
    to_item_id: int | None = Field(None, ge=1)
    to_fsku_id: int | None = Field(None, ge=1)
    reason: str | None = Field(None, max_length=200)

    @model_validator(mode="after")
    def _xor_target(self) -> "BindingMigrateIn":
        has_item = self.to_item_id is not None
        has_fsku = self.to_fsku_id is not None
        if has_item == has_fsku:
            raise ValueError("to_item_id 与 to_fsku_id 必须二选一（且只能选一个）")
        return self


class BindingMigrateOut(BaseModel):
    current: BindingRow
