# app/oms/orders/contracts/order_outbound_view.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class OrderOutboundViewOrderOut(BaseModel):
    """
    订单出库页专用：订单头只读模型（来源真相 = orders）

    说明：
    - 这里只表达真实订单头字段
    - 不掺执行仓 / 履约阶段 / 出库状态投影
    - order_fulfillment 后续若要展示，单独做 execution_context，不混入这里
    """

    model_config = ConfigDict(extra="ignore")

    id: int
    platform: str
    shop_id: str
    ext_order_no: str

    status: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    buyer_name: Optional[str] = None
    buyer_phone: Optional[str] = None

    order_amount: Optional[Decimal] = None
    pay_amount: Optional[Decimal] = None


class OrderOutboundViewLineOut(BaseModel):
    """
    订单出库页专用：订单行只读模型（来源真相 = order_lines）

    说明：
    - 当前只返回真实 order_lines 稳定字段
    - 不脑补商品名 / 规格 / 单位
    - 若后续页面需要展示增强，另做 item_display 块，不污染订单来源合同
    """

    model_config = ConfigDict(extra="ignore")

    id: int
    order_id: int
    item_id: int
    req_qty: int


class OrderOutboundViewResponse(BaseModel):
    """
    订单出库页专用：只读聚合响应

    结构：
    - order: 订单头（orders）
    - lines: 订单行（order_lines）
    """

    model_config = ConfigDict(extra="ignore")

    ok: bool = True
    order: OrderOutboundViewOrderOut
    lines: List[OrderOutboundViewLineOut] = Field(default_factory=list)
