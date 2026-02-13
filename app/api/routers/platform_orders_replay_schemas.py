# app/api/routers/platform_orders_replay_schemas.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, constr


class PlatformOrderReplayIn(BaseModel):
    """
    平台订单事实重放解码（内部治理接口）：
    - 入参接收 store_id（stores.id）
    - 读取 platform_order_lines 事实行
    - 复用 resolver + /orders ingest 主线幂等生成订单

    Phase DRILL 双宇宙要求：
    - scope 必须显式给出，或可从平台订单地址事实表 platform_order_addresses 唯一推断
    - address 优先从 platform_order_addresses 回读（事实锚点），payload.address 仅作为显式覆盖
    """

    model_config = ConfigDict(extra="ignore")

    platform: constr(min_length=1, max_length=32)
    store_id: int = Field(..., ge=1)
    ext_order_no: constr(min_length=1)

    # ✅ 推荐显式传入：DRILL / PROD
    scope: Optional[constr(min_length=1, max_length=16)] = None

    # ✅ 可选覆盖（默认仍应从 platform_order_addresses 回读）
    address: Optional[Dict[str, Any]] = None


class PlatformOrderReplayOut(BaseModel):
    status: str
    id: Optional[int] = None
    ref: str

    platform: str
    store_id: int
    ext_order_no: str

    facts_n: int = 0
    resolved: List[Dict[str, Any]] = Field(default_factory=list)
    unresolved: List[Dict[str, Any]] = Field(default_factory=list)

    fulfillment_status: Optional[str] = None
    blocked_reasons: Optional[List[str]] = None
