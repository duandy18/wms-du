# app/api/schemas/fsku.py
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class FskuCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    unit_label: str | None = Field(None, max_length=50)


# Phase A：role 扩展为 primary/gift（只表达语义，不引入履约裁决）
FskuComponentRole = Literal["primary", "gift"]


class FskuComponentIn(BaseModel):
    item_id: int = Field(..., ge=1)
    # ✅ 契约刚性：qty 是“数量”，必须为正整数（避免 2.0/2.5 漂移）
    qty: int = Field(..., ge=1)
    # ✅ 合同刚性：仅允许 primary/gift（表达“主销/赠品”）
    role: FskuComponentRole


class FskuComponentsReplaceIn(BaseModel):
    components: list[FskuComponentIn]


class FskuComponentOut(BaseModel):
    item_id: int
    qty: int
    role: FskuComponentRole


class FskuDetailOut(BaseModel):
    id: int
    name: str
    unit_label: str | None
    status: str
    published_at: datetime | None
    retired_at: datetime | None
    created_at: datetime
    updated_at: datetime
    components: list[FskuComponentOut]


class FskuListItem(BaseModel):
    id: int
    name: str
    unit_label: str | None
    status: str
    updated_at: datetime


class FskuListOut(BaseModel):
    items: list[FskuListItem]
    total: int
    limit: int
    offset: int
