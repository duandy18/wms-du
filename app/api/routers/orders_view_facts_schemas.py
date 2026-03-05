# app/api/routers/orders_view_facts_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class PlatformOrderLineOut(BaseModel):
    """
    平台订单“原始行”（镜像用）
    只输出平台侧可理解字段，不输出作业字段。

    Phase 5+ 镜像口径：
    - 基础字段来自 order_items：item_id/sku_id/title/qty/price/discount/amount/extras
    - extras（JSONB）用于承载平台原始字段（规格、属性、平台 SKU 信息等）
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
    字段命名对齐你们 ingest 的 receiver_* / province/city/district/detail
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

    raw：
    - 为详情页/排障保留的“原始包”（orders/order_items/order_address 原始行的 json-friendly 版本）
    - 不携带履约累积语义（shipped/returned 等）
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
    items: List[PlatformOrderLineOut] = []

    raw: Optional[Dict[str, Any]] = None


class OrderViewResponse(BaseModel):
    ok: bool = True
    order: PlatformOrderOut


class OrderFactItemOut(BaseModel):
    """
    facts：订单镜像的“数量事实”（只读、无履约语义）。

    说明：
    - 镜像详情里“数量”有意义（qty_ordered）
    - shipped/returned 等履约累积字段对“平台镜像详情”无意义，因此不输出
    """

    model_config = ConfigDict(extra="ignore")

    item_id: int
    sku_id: Optional[str] = None
    title: Optional[str] = None

    qty_ordered: int = 0


class OrderFactsResponse(BaseModel):
    ok: bool = True
    items: List[OrderFactItemOut]
