# app/api/routers/orders.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, constr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers import orders_availability_routes, orders_summary_routes
from app.api.routers import orders_view_facts_routes
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


class OrderFulfillmentOut(BaseModel):
    """
    Phase 5.2：履约事实快照（产品化输出）

    兼容字段名（对外）：
    - service_warehouse_id：服务归属仓（planned_warehouse_id）
    - warehouse_id：执行出库仓（actual_warehouse_id）
    - fulfillment_status：履约状态（SERVICE_ASSIGNED / READY_TO_FULFILL / MANUALLY_ASSIGNED / BLOCKED）

    ✅ 系统事实来源：order_fulfillment
    """

    service_warehouse_id: Optional[int] = None
    warehouse_id: Optional[int] = None
    fulfillment_status: Optional[str] = None

    route_status: Optional[str] = None
    ingest_state: Optional[str] = None
    auto_assign_status: Optional[str] = None


class OrderCreateOut(BaseModel):
    status: str
    id: Optional[int] = None
    ref: str

    # ✅ Phase 5.2：把关键履约事实带出去（前端/运营不必再查 DB）
    fulfillment: Optional[OrderFulfillmentOut] = None


async def _load_fulfillment_snapshot(session: AsyncSession, *, order_id: int) -> Dict[str, Any]:
    """
    从 order_fulfillment 表读取履约事实快照（以 DB 为准）。

    兼容输出字段名：
      - service_warehouse_id := planned_warehouse_id
      - warehouse_id := actual_warehouse_id
    """
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                      planned_warehouse_id,
                      actual_warehouse_id,
                      fulfillment_status
                    FROM order_fulfillment
                    WHERE order_id = :oid
                    LIMIT 1
                    """
                ),
                {"oid": int(order_id)},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return {"service_warehouse_id": None, "warehouse_id": None, "fulfillment_status": None}

    return {
        "service_warehouse_id": int(row["planned_warehouse_id"]) if row.get("planned_warehouse_id") is not None else None,
        "warehouse_id": int(row["actual_warehouse_id"]) if row.get("actual_warehouse_id") is not None else None,
        "fulfillment_status": str(row["fulfillment_status"]) if row.get("fulfillment_status") is not None else None,
    }


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

    # 4) 提交，确保写入可见
    await session.commit()

    # 5) 组装 Phase 5.2 履约快照（DB 事实 + ingest 解释字段）
    oid = int(r.get("id") or 0) if r.get("id") is not None else None
    fulfillment: Optional[OrderFulfillmentOut] = None
    if oid:
        snap = await _load_fulfillment_snapshot(session, order_id=oid)
        auto_assign = r.get("auto_assign") or {}
        fulfillment = OrderFulfillmentOut(
            service_warehouse_id=snap.get("service_warehouse_id"),
            warehouse_id=snap.get("warehouse_id"),
            fulfillment_status=snap.get("fulfillment_status"),
            route_status=str(r.get("route_status")) if r.get("route_status") is not None else None,
            ingest_state=str(r.get("ingest_state")) if r.get("ingest_state") is not None else None,
            auto_assign_status=str(auto_assign.get("status")) if auto_assign.get("status") is not None else None,
        )

    return OrderCreateOut(status=str(r.get("status") or "OK"), id=oid, ref=str(r.get("ref")), fulfillment=fulfillment)


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

    oid = int(r.get("id") or 0) if r.get("id") is not None else None
    fulfillment: Optional[OrderFulfillmentOut] = None
    if oid:
        snap = await _load_fulfillment_snapshot(session, order_id=oid)
        auto_assign = r.get("auto_assign") or {}
        fulfillment = OrderFulfillmentOut(
            service_warehouse_id=snap.get("service_warehouse_id"),
            warehouse_id=snap.get("warehouse_id"),
            fulfillment_status=snap.get("fulfillment_status"),
            route_status=str(r.get("route_status")) if r.get("route_status") is not None else None,
            ingest_state=str(r.get("ingest_state")) if r.get("ingest_state") is not None else None,
            auto_assign_status=str(auto_assign.get("status")) if auto_assign.get("status") is not None else None,
        )

    return OrderCreateOut(status=str(r.get("status") or "OK"), id=oid, ref=str(r.get("ref")), fulfillment=fulfillment)


# ✅ Phase 5.2：订单管理列表（正统出口）
# 注入 /orders/summary，确保 orders 域只有一个 router 作为权威出口
orders_summary_routes.register(router)

# ✅ 平台订单镜像（view/facts，只读）
orders_view_facts_routes.register(router)

# ✅ Phase 5.3：订单 × 仓库库存对齐（Explain 层，只读）
orders_availability_routes.register(router)
