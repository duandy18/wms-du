# app/schemas/reserve_soft.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


# -------------------------------
# 通用行结构
# -------------------------------
class ReserveLineIn(BaseModel):
    item_id: int
    qty: int


# -------------------------------
# /reserve/persist 入口/出口
# -------------------------------
class ReservePersistIn(BaseModel):
    platform: str  # 例如 "PDD" / "pdd"
    shop_id: str  # 统一用字符串，测试里也是 "1"
    warehouse_id: int
    ref: str
    lines: List[ReserveLineIn]
    expire_at: Optional[datetime] = None  # 目前服务里没真正用到，只做透传占位


class ReservePersistOut(BaseModel):
    status: str  # "OK"
    reservation_id: int
    ref: str
    idempotent: bool


# -------------------------------
# /reserve/pick/commit 入口/出口
# -------------------------------
class ReservePickIn(BaseModel):
    platform: str
    shop_id: str
    warehouse_id: int
    ref: str
    occurred_at: Optional[datetime] = None


class ReservePickOut(BaseModel):
    status: str  # "CONSUMED" / "NOOP" / "PARTIAL"（目前我们只返回 CONSUMED/NOOP）
    ref: str
    consumed: Optional[int] = None
    reason: Optional[str] = None


# -------------------------------
# /reserve/release 入口/出口
# -------------------------------
class ReserveReleaseIn(BaseModel):
    platform: str
    shop_id: str
    warehouse_id: int
    ref: str


class ReserveReleaseOut(BaseModel):
    status: str  # "CANCELED" / "NOOP"
    ref: str
    reason: Optional[str] = None
