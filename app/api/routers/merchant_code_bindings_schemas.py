# app/api/routers/merchant_code_bindings_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MerchantCodeBindingBindIn(BaseModel):
    platform: str = Field(..., min_length=1, max_length=32, description="平台（DEMO/PDD/TB...）")
    shop_id: str = Field(..., min_length=1, max_length=64, description="平台店铺 ID（与 platform 对齐）")
    merchant_code: str = Field(..., min_length=1, max_length=128, description="商家规格编码（filled_code）")
    fsku_id: int = Field(..., ge=1, description="要绑定到的 published FSKU.id")
    reason: Optional[str] = Field(None, max_length=500, description="绑定原因（可选）")


class MerchantCodeBindingOut(BaseModel):
    ok: bool = True
    data: dict


def to_out_row(
    *,
    id: int,
    platform: str,
    shop_id: int,
    merchant_code: str,
    fsku_id: int,
    effective_from: datetime,
    effective_to: Optional[datetime],
    reason: Optional[str],
    created_at: datetime,
) -> dict:
    return {
        "id": int(id),
        "platform": platform,
        "shop_id": int(shop_id),
        "merchant_code": merchant_code,
        "fsku_id": int(fsku_id),
        "effective_from": effective_from,
        "effective_to": effective_to,
        "reason": reason,
        "created_at": created_at,
    }
