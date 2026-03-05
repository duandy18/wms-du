# app/api/schemas/fsku.py
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


FskuShape = Literal["single", "bundle"]


class FskuCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)

    # ✅ FSKU 编码：像 items.sku 一样重要
    # 允许不传：后端会生成 FSKU-{id}
    code: str | None = Field(None, min_length=1, max_length=64)

    # ✅ 商品形态（与 DB ck_fskus_shape 对齐）
    shape: FskuShape = Field("bundle")


class FskuNameUpdateIn(BaseModel):
    # ✅ 运营可读名：允许修改（draft/published 可改；retired 只读由 service 护栏）
    name: str = Field(..., min_length=1, max_length=200)


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
    code: str
    name: str
    shape: FskuShape
    status: str
    published_at: datetime | None
    retired_at: datetime | None
    created_at: datetime
    updated_at: datetime
    components: list[FskuComponentOut]


class FskuListItem(BaseModel):
    id: int
    code: str
    name: str
    shape: FskuShape
    status: str
    updated_at: datetime

    # ✅ 归档/发布信息（列表直接展示用）
    published_at: datetime | None
    retired_at: datetime | None

    # ✅ 列表用：组合内容摘要（由后端聚合出来）
    # - components_summary: 工程排查用（SKU 版）
    # - components_summary_name: 运营/治理用（主数据商品名版）
    components_summary: str
    components_summary_name: str


class FskuListOut(BaseModel):
    items: list[FskuListItem]
    total: int
    limit: int
    offset: int
