# app/api/schemas/platform_sku_binding.py
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BindingCreateIn(BaseModel):
    platform: str = Field(..., min_length=1, max_length=50)
    shop_id: int = Field(..., ge=1)
    platform_sku_id: str = Field(..., min_length=1, max_length=200)

    # ✅ 单入口收敛：仅允许绑定到 FSKU
    # 单品也必须用 single-FSKU 承载（由 FSKU.components 指向 item）
    fsku_id: int = Field(..., ge=1)

    reason: str | None = Field(None, max_length=200)


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

    # 历史兼容：旧数据可能存在 item_id（legacy），读历史时仍可返回
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
    # ✅ 单入口收敛：仅允许迁移到 FSKU
    to_fsku_id: int = Field(..., ge=1)
    reason: str | None = Field(None, max_length=200)


class BindingMigrateOut(BaseModel):
    current: BindingRow
