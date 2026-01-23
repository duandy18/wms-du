# app/api/routers/devconsole_orders_routes_reconcile.py
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.devconsole_orders_schemas import (
    DevEnsureWarehouseOut,
    DevOrderReconcileLine,
    DevOrderReconcileResultModel,
    DevReconcileRangeResult,
)
from app.services.order_reconcile_service import OrderReconcileService


def register(router: APIRouter) -> None:
    # ------------------------- 对账 ------------------------- #

    @router.get("/by-id/{order_id}/reconcile", response_model=DevOrderReconcileResultModel)
    async def reconcile_order_by_id(
        order_id: int,
        session: AsyncSession = Depends(get_session),
    ) -> DevOrderReconcileResultModel:
        svc = OrderReconcileService(session)
        res = await svc.reconcile_order(order_id)

        lines = [
            DevOrderReconcileLine(
                item_id=lf.item_id,
                sku_id=lf.sku_id,
                title=lf.title,
                qty_ordered=lf.qty_ordered,
                qty_shipped=lf.qty_shipped,
                qty_returned=lf.qty_returned,
                remaining_refundable=lf.remaining_refundable,
            )
            for lf in res.lines
        ]

        return DevOrderReconcileResultModel(
            order_id=res.order_id,
            platform=res.platform,
            shop_id=res.shop_id,
            ext_order_no=res.ext_order_no,
            issues=res.issues,
            lines=lines,
        )

    # ------------------------- 范围修账 ------------------------- #

    @router.post("/reconcile-range", response_model=DevReconcileRangeResult)
    async def reconcile_orders_range(
        time_from: datetime = Query(...),
        time_to: datetime = Query(...),
        limit: int = Query(200, ge=1, le=1000),
        session: AsyncSession = Depends(get_session),
    ) -> DevReconcileRangeResult:
        svc = OrderReconcileService(session)
        results = await svc.reconcile_orders_by_created_at(
            time_from=time_from,
            time_to=time_to,
            limit=limit,
        )

        for res in results:
            await svc.apply_counters(res.order_id)

        await session.commit()

        return DevReconcileRangeResult(
            count=len(results),
            order_ids=[r.order_id for r in results],
        )

    # ------------------------- ensure warehouse（已禁用） ------------------------- #

    @router.post(
        "/{platform}/{shop_id}/{ext_order_no}/ensure-warehouse",
        response_model=DevEnsureWarehouseOut,
    )
    async def ensure_order_warehouse_disabled(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        session: AsyncSession = Depends(get_session),
    ) -> DevEnsureWarehouseOut:
        """
        Phase 5.1：devconsole 不允许写 orders.warehouse_id（禁止隐性回填/后门写入）。

        ✅ 正确做法：
        - 走订单履约 API：/orders/{platform}/{shop_id}/{ext}/fulfillment/manual-assign
        - 或使用离线脚本（仅本地/运维）：scripts/dev_set_order_warehouse.py
        """
        _ = (platform, shop_id, ext_order_no, session)
        raise HTTPException(
            status_code=410,
            detail=(
                "devconsole ensure-warehouse is disabled in Phase 5.1. "
                "Use /orders/{platform}/{shop_id}/{ext}/fulfillment/manual-assign "
                "or run scripts/dev_set_order_warehouse.py."
            ),
        )
