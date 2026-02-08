from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class PlatformSkuBindingSummary(BaseModel):
    status: Literal["bound", "unbound"]

    # ✅ 列表增强：如果存在 current binding，则带出 binding_id（用于 migrate）
    # - unbound 时为 None
    binding_id: Optional[int] = None

    # ✅ 单入口：只允许绑定到 fsku
    target_type: Optional[Literal["fsku"]] = None
    fsku_id: Optional[int] = None
    effective_from: Optional[datetime] = None


class PlatformSkuListItem(BaseModel):
    platform: str

    # ✅ 新合同：内部治理一律用 store_id（stores.id）
    store_id: int

    # ⚠️ 兼容字段：历史合同名 shop_id（语义等同于 store_id）
    # - 兼容期保留；前端/新调用方请改用 store_id
    shop_id: int

    platform_sku_id: str
    sku_name: Optional[str] = None

    binding: PlatformSkuBindingSummary


class PlatformSkuListOut(BaseModel):
    items: list[PlatformSkuListItem]
    total: int
    limit: int
    offset: int
