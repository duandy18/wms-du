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
    store_code: str
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
    订单出库页专用：订单行只读模型（来源真相 = order_lines + item display）

    说明：
    - 核心真相仍然是 order_lines
    - 为作业页补充商品展示字段：sku / name / spec / base_uom
    - 不掺平台 ledger / 执行上下文 / lot 分配结果
    """

    model_config = ConfigDict(extra="ignore")

    id: int
    order_id: int
    item_id: int
    req_qty: int

    item_sku: Optional[str] = None
    item_name: Optional[str] = None
    item_spec: Optional[str] = None

    base_uom_id: Optional[int] = None
    base_uom_name: Optional[str] = None


class OrderOutboundViewResponse(BaseModel):
    """
    订单出库页专用：只读聚合响应

    结构：
    - order: 订单头（orders）
    - lines: 订单行（order_lines + display）
    """

    model_config = ConfigDict(extra="ignore")

    ok: bool = True
    order: OrderOutboundViewOrderOut
    lines: List[OrderOutboundViewLineOut] = Field(default_factory=list)
