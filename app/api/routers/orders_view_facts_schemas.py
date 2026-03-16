# app/api/routers/orders_view_facts_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PlatformOrderLineOut(BaseModel):
    """
    平台订单“原始行”（镜像用）
    只输出平台侧可理解字段，不输出作业字段。
    """

    model_config = ConfigDict(extra="ignore")

    sku: Optional[str] = None
    title: Optional[str] = None
    qty: int = 0
    item_id: Optional[int] = None
    spec: Optional[str] = None

    # 价格/金额：镜像展示用（不参与作业逻辑）
    price: Optional[float] = None
    discount: Optional[float] = None
    amount: Optional[float] = None

    # 平台原始扩展字段（JSONB）
    extras: Optional[Dict[str, Any]] = None


class PlatformOrderAddressOut(BaseModel):
    """
    平台订单收件信息（镜像用）
    """

    model_config = ConfigDict(extra="ignore")

    receiver_name: Optional[str] = None
    receiver_phone: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    detail: Optional[str] = None
    zipcode: Optional[str] = None


class PlatformOrderOut(BaseModel):
    """
    平台订单“镜像头” + “原始行 items”
    """

    model_config = ConfigDict(extra="ignore")

    id: int
    platform: str
    shop_id: str
    ext_order_no: str
    status: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    order_amount: Optional[float] = None
    pay_amount: Optional[float] = None

    buyer_name: Optional[str] = None
    buyer_phone: Optional[str] = None

    address: Optional[PlatformOrderAddressOut] = None
    items: List[PlatformOrderLineOut] = Field(default_factory=list)

    raw: Optional[Dict[str, Any]] = None


class OrderViewResponse(BaseModel):
    ok: bool = True
    order: PlatformOrderOut


class OrderFactItemOut(BaseModel):
    """
    正式 orders facts 合同（完整版）

    含义：
    - qty_ordered：订单行要求数量
    - qty_shipped：已出库数量（按 stock_ledger 汇总）
    - qty_returned：已回仓数量（按 inbound_receipts / lines 汇总）
    - qty_remaining_refundable：剩余可退货数量
    """

    model_config = ConfigDict(extra="ignore")

    item_id: int
    sku_id: Optional[str] = None
    title: Optional[str] = None

    qty_ordered: int = 0
    qty_shipped: int = 0
    qty_returned: int = 0
    qty_remaining_refundable: int = 0


class OrderFactsResponse(BaseModel):
    ok: bool = True
    order_id: int
    platform: str
    shop_id: str
    ext_order_no: str
    issues: List[str] = Field(default_factory=list)
    items: List[OrderFactItemOut] = Field(default_factory=list)
