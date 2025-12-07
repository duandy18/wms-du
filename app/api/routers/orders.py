# app/api/routers/orders.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, constr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.audit import new_trace
from app.services.order_service import OrderService
from app.services.store_service import StoreService

router = APIRouter(tags=["orders"])

# 放宽：任意非空字符串都可作为平台标识（服务层会统一 upper）
PlatformStr = constr(min_length=1, max_length=32)


class OrderLineIn(BaseModel):
    """更宽松的行项目：只必需 qty，其他字段尽量可选，服务层自行兜底"""

    model_config = ConfigDict(extra="ignore")
    sku_id: Optional[str] = None
    item_id: Optional[int] = None
    title: Optional[str] = None
    qty: int = Field(default=1, gt=0)
    price: Optional[float] = 0.0
    discount: Optional[float] = 0.0
    amount: Optional[float] = 0.0


class OrderAddrIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    receiver_name: Optional[str] = None
    receiver_phone: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    detail: Optional[str] = None
    zipcode: Optional[str] = None


class OrderCreateIn(BaseModel):
    """标准口径：最小必填 platform/shop_id/ext_order_no，其余尽量宽松。"""

    model_config = ConfigDict(extra="ignore")
    platform: PlatformStr
    shop_id: constr(min_length=1)
    ext_order_no: constr(min_length=1)
    occurred_at: Optional[datetime] = None
    buyer_name: Optional[str] = None
    buyer_phone: Optional[str] = None
    order_amount: Optional[float] = 0.0
    pay_amount: Optional[float] = 0.0
    lines: List[OrderLineIn] = Field(default_factory=list)
    address: Optional[OrderAddrIn] = None
    # 可选：便于接单时自动补录店铺名称
    store_name: Optional[str] = None


class OrderCreateOut(BaseModel):
    status: str
    id: Optional[int] = None
    ref: str


@router.post("/orders", response_model=OrderCreateOut)
async def create_order(
    payload: OrderCreateIn,
    session: AsyncSession = Depends(get_session),
):
    # 1) 先自动补录店铺（幂等 UPSERT），保证“接单即建档”
    plat = payload.platform.upper()
    await StoreService.ensure_store(
        session,
        platform=plat,
        shop_id=payload.shop_id,
        name=payload.store_name or f"{plat}-{payload.shop_id}",
    )

    # 2) 为本次 /orders 调用生成 trace_id
    trace = new_trace("http:/orders")

    # 3) 交由服务层落库 + 审计（幂等）
    r = await OrderService.ingest(
        session,
        platform=payload.platform,  # ingest 内部会统一 upper()
        shop_id=payload.shop_id,
        ext_order_no=payload.ext_order_no,
        occurred_at=payload.occurred_at,
        buyer_name=payload.buyer_name,
        buyer_phone=payload.buyer_phone,
        order_amount=payload.order_amount or 0.0,
        pay_amount=payload.pay_amount or 0.0,
        items=[l.model_dump() for l in (payload.lines or [])],
        address=payload.address.model_dump() if payload.address else None,
        extras=None,
        trace_id=trace.trace_id,
    )

    # 4) 提交，确保后续读取（例如测试里立即查询 stores）可见
    await session.commit()
    return OrderCreateOut(**r)


@router.post("/orders/raw", response_model=OrderCreateOut)
async def create_order_raw(
    platform: PlatformStr = Query(..., description="平台标识（任意非空字符串）"),
    shop_id: constr(min_length=1) = Query(...),
    payload: Dict[str, Any] = Body(..., description="平台原始订单 JSON；多余字段将被忽略"),
    session: AsyncSession = Depends(get_session),
):
    # 同样先自动补录店铺
    plat = platform.upper()
    await StoreService.ensure_store(session, platform=plat, shop_id=shop_id)

    # 为原始订单生成独立 trace
    trace = new_trace("http:/orders/raw")

    r = await OrderService.ingest_raw(
        session, platform=platform, shop_id=shop_id, payload=payload, trace_id=trace.trace_id
    )
    await session.commit()
    return OrderCreateOut(**r)
