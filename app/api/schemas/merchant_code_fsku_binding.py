# app/api/schemas/merchant_code_fsku_binding.py
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MerchantCodeBindingCreateIn(BaseModel):
    platform: str = Field(..., min_length=1, max_length=32)
    shop_id: int = Field(..., ge=1)
    merchant_code: str = Field(..., min_length=1, max_length=128)
    fsku_id: int = Field(..., ge=1)
    reason: str | None = Field(None, max_length=500)


class MerchantCodeBindingOut(BaseModel):
    id: int
    platform: str
    shop_id: int
    merchant_code: str
    fsku_id: int
    effective_from: datetime
    effective_to: datetime | None
    reason: str | None
    created_at: datetime


# 订单解析失败分型（第一版就够用）
MerchantCodeResolveError = Literal[
    "MISSING_CODE",
    "INVALID_CODE_FORMAT",
    "CODE_NOT_BOUND",
    "FSKU_NOT_PUBLISHED",
]


class MerchantCodeResolveResult(BaseModel):
    ok: bool
    error: MerchantCodeResolveError | None = None
    fsku_id: int | None = None
