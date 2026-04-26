# app/oms/orders/contracts/order_outbound_options.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class OrderOutboundOptionOut(BaseModel):
    """
    订单出库页专用：订单选择器列表项（来源真相 = orders）

    说明：
    - 只返回“选单”需要的最小头字段
    - 不掺执行仓 / 履约阶段 / 平台 ledger 明细
    """

    model_config = ConfigDict(extra="ignore")

    id: int
    platform: str
    store_code: str
    ext_order_no: str

    status: Optional[str] = None
    buyer_name: Optional[str] = None
    created_at: datetime


class OrderOutboundOptionsOut(BaseModel):
    """
    订单出库页专用：订单选择器列表响应
    """

    model_config = ConfigDict(extra="ignore")

    items: List[OrderOutboundOptionOut] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
