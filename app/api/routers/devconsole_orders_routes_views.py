# app/api/routers/devconsole_orders_routes_views.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.devconsole_orders_schemas import (
    DevOrderFacts,
    DevOrderInfo,
    DevOrderItemFact,
    DevOrderSummary,
    DevOrderView,
)
from app.services.dev_orders_service import DevOrdersService


def register(router: APIRouter) -> None:
    # ------------------------- 单订单头部 ------------------------- #

    @router.get("/{platform}/{shop_id}/{ext_order_no}", response_model=DevOrderView)
    async def get_dev_order_view(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        session: AsyncSession = Depends(get_session),
    ) -> DevOrderView:
        svc = DevOrdersService(session)
        head = await svc.get_order_head(platform, shop_id, ext_order_no)

        if head is None:
            raise HTTPException(404, "order not found")

        order = DevOrderInfo(
            id=head["id"],
            platform=head["platform"],
            shop_id=head["shop_id"],
            ext_order_no=head["ext_order_no"],
            status=head.get("status"),
            trace_id=head.get("trace_id"),
            created_at=head["created_at"],
            updated_at=head.get("updated_at"),
            warehouse_id=head.get("warehouse_id"),
            order_amount=float(head["order_amount"]) if head.get("order_amount") else None,
            pay_amount=float(head["pay_amount"]) if head.get("pay_amount") else None,
        )

        return DevOrderView(order=order, trace_id=order.trace_id)

    # ------------------------- facts ------------------------- #

    @router.get("/{platform}/{shop_id}/{ext_order_no}/facts", response_model=DevOrderFacts)
    async def get_dev_order_facts(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        session: AsyncSession = Depends(get_session),
    ) -> DevOrderFacts:
        svc = DevOrdersService(session)
        head, items = await svc.get_order_facts(platform, shop_id, ext_order_no)

        order = DevOrderInfo(
            id=head["id"],
            platform=head["platform"],
            shop_id=head["shop_id"],
            ext_order_no=head["ext_order_no"],
            status=head.get("status"),
            trace_id=head.get("trace_id"),
            created_at=head["created_at"],
            updated_at=head.get("updated_at"),
            warehouse_id=head.get("warehouse_id"),
            order_amount=float(head["order_amount"]) if head.get("order_amount") else None,
            pay_amount=float(head["pay_amount"]) if head.get("pay_amount") else None,
        )

        facts = [
            DevOrderItemFact(
                item_id=it["item_id"],
                sku_id=it.get("sku_id"),
                title=it.get("title"),
                qty_ordered=it["qty_ordered"],
                qty_shipped=it["qty_shipped"],
                qty_returned=it["qty_returned"],
                qty_remaining_refundable=it["qty_remaining_refundable"],
            )
            for it in items
        ]

        return DevOrderFacts(order=order, items=facts)

    # ------------------------- summary 列表 ------------------------- #

    @router.get("", response_model=List[DevOrderSummary])
    async def list_orders_summary(
        session: AsyncSession = Depends(get_session),
        platform: Optional[str] = Query(None),
        shop_id: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
        time_from: Optional[object] = Query(None),
        time_to: Optional[object] = Query(None),
        limit: int = Query(100),
    ) -> List[DevOrderSummary]:
        # NOTE: 这里 time_from/time_to 在原文件里是 datetime|None，
        # 但 FastAPI/Query 在拆分中保持参数名/默认值不变即可。
        # 为避免类型争议，本文件不强化注解；具体类型由 FastAPI runtime 负责解析。
        svc = DevOrdersService(session)
        rows = await svc.list_orders_summary(
            platform=platform,
            shop_id=shop_id,
            status=status,
            time_from=time_from,  # type: ignore[arg-type]
            time_to=time_to,  # type: ignore[arg-type]
            limit=limit,
        )

        return [
            DevOrderSummary(
                id=r["id"],
                platform=r["platform"],
                shop_id=r["shop_id"],
                ext_order_no=r["ext_order_no"],
                status=r.get("status"),
                created_at=r["created_at"],
                updated_at=r.get("updated_at"),
                warehouse_id=r.get("warehouse_id"),
                order_amount=float(r["order_amount"]) if r.get("order_amount") else None,
                pay_amount=float(r["pay_amount"]) if r.get("pay_amount") else None,
            )
            for r in rows
        ]
