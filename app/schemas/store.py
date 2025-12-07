# app/schemas/store.py

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class RouteMode(str, Enum):
    STRICT_TOP = "STRICT_TOP"
    FALLBACK = "FALLBACK"


class StoreSummary(BaseModel):
    """
    简要店铺信息（用于列表视图）。
    """

    id: int
    platform: str
    shop_id: str
    name: str
    active: bool = True
    route_mode: RouteMode = RouteMode.STRICT_TOP


class StoreWarehouseBinding(BaseModel):
    """
    店铺与仓库的绑定关系（主仓 / 备仓 / 优先级）。
    """

    warehouse_id: int
    is_top: bool
    is_default: Optional[bool] = None
    priority: int

    class Config:
        orm_mode = True


class StoreDetail(StoreSummary):
    """
    店铺详情：在 StoreSummary 基础上附带仓库绑定列表。
    """

    warehouses: List[StoreWarehouseBinding]


class StorePlatformAuthStatus(BaseModel):
    """
    店铺在平台维度的授权状态视图。

    - auth_source:
        * "NONE"   : 没有任何 token 记录
        * "MANUAL" : 通过 /platform-shops/credentials 手工录入
        * "OAUTH"  : 通过 OAuth 回调写入 store_tokens
    """

    store_id: int
    platform: str
    shop_id: str
    auth_source: str  # "NONE" / "MANUAL" / "OAUTH"
    expires_at: Optional[datetime] = None
    mall_id: Optional[str] = None
