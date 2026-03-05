# app/api/routers/merchant_code_bindings_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MerchantCodeBindingBindIn(BaseModel):
    platform: str = Field(..., min_length=1, max_length=32, description="平台（DEMO/PDD/TB...）")
    shop_id: str = Field(..., min_length=1, max_length=64, description="平台店铺 ID（字符串，与 platform 对齐）")
    merchant_code: str = Field(..., min_length=1, max_length=128, description="商家后端规格编码（merchant_code / filled_code）")
    fsku_id: int = Field(..., ge=1, description="要绑定到的 published FSKU.id")
    reason: Optional[str] = Field(None, max_length=500, description="绑定原因（可选）")


class MerchantCodeBindingCloseIn(BaseModel):
    platform: str = Field(..., min_length=1, max_length=32, description="平台（DEMO/PDD/TB...）")
    shop_id: str = Field(..., min_length=1, max_length=64, description="平台店铺 ID（字符串，与 platform 对齐）")
    merchant_code: str = Field(..., min_length=1, max_length=128, description="商家后端规格编码（merchant_code / filled_code）")


class MerchantCodeBindingQueryIn(BaseModel):
    platform: Optional[str] = Field(None, min_length=1, max_length=32, description="平台（精确）")
    shop_id: Optional[str] = Field(None, min_length=1, max_length=64, description="平台店铺 ID（精确，字符串）")
    merchant_code: Optional[str] = Field(None, min_length=1, max_length=128, description="商家后端规格编码（模糊 contains）")
    # ✅ current_only 作为兼容字段保留，但简化模型下恒等于 true（无历史、无 effective_to）
    current_only: bool = Field(True, description="兼容字段：简化模型下恒等于 true")
    fsku_id: Optional[int] = Field(None, ge=1, description="按 fsku_id 精确过滤")
    fsku_code: Optional[str] = Field(None, min_length=1, max_length=64, description="按 fsku.code 过滤（contains）")
    limit: int = Field(50, ge=1, le=200, description="分页大小")
    offset: int = Field(0, ge=0, description="分页偏移")


class StoreLiteOut(BaseModel):
    id: int
    name: str


class FskuLiteOut(BaseModel):
    id: int
    code: str
    name: str
    status: str


class MerchantCodeBindingRowOut(BaseModel):
    id: int
    platform: str
    shop_id: str

    # ✅ join 展示字段（不落绑定表）
    store: StoreLiteOut

    merchant_code: str
    fsku_id: int
    fsku: FskuLiteOut

    reason: Optional[str]
    created_at: datetime
    updated_at: datetime


class MerchantCodeBindingOut(BaseModel):
    ok: bool = True
    data: MerchantCodeBindingRowOut


class MerchantCodeBindingListDataOut(BaseModel):
    items: list[MerchantCodeBindingRowOut]
    total: int
    limit: int
    offset: int


class MerchantCodeBindingListOut(BaseModel):
    ok: bool = True
    data: MerchantCodeBindingListDataOut
