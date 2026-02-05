# app/api/schemas/fsku.py
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class FskuCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    unit_label: str | None = Field(None, max_length=50)


class FskuComponentIn(BaseModel):
    item_id: int = Field(..., ge=1)
    qty: float = Field(..., gt=0)
    role: str = Field(..., min_length=1, max_length=50)


class FskuComponentsReplaceIn(BaseModel):
    components: list[FskuComponentIn]


class FskuComponentOut(BaseModel):
    item_id: int
    qty: float
    role: str


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
