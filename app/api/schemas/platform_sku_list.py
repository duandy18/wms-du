from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class PlatformSkuBindingSummary(BaseModel):
    status: Literal["bound", "unbound"]
    target_type: Optional[Literal["item", "fsku"]] = None
    item_id: Optional[int] = None
    fsku_id: Optional[int] = None
    effective_from: Optional[datetime] = None


class PlatformSkuListItem(BaseModel):
    platform: str
    shop_id: int
    platform_sku_id: str
    sku_name: Optional[str] = None

    binding: PlatformSkuBindingSummary


class PlatformSkuListOut(BaseModel):
    items: list[PlatformSkuListItem]
    total: int
    limit: int
    offset: int
