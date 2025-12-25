# app/api/routers/devconsole_orders_routes_reconcile.py
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.devconsole_orders_schemas import (
    DevEnsureWarehouseOut,
    DevOrderReconcileLine,
    DevOrderReconcileResultModel,
    DevReconcileRangeResult,
)
from app.services.order_reconcile_service import OrderReconcileService
from app.services.store_service import StoreService


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

    # ------------------------- ensure warehouse ------------------------- #

    @router.post(
        "/{platform}/{shop_id}/{ext_order_no}/ensure-warehouse",
        response_model=DevEnsureWarehouseOut,
    )
    async def ensure_order_warehouse(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        session: AsyncSession = Depends(get_session),
    ) -> DevEnsureWarehouseOut:
        plat = platform.upper()

        # 查订单
        row = (
            (
                await session.execute(
                    text(
                        """
                    SELECT id, warehouse_id
                      FROM orders
                     WHERE platform=:p
                       AND shop_id=:s
                       AND ext_order_no=:o
                     LIMIT 1
                    """
                    ),
                    {"p": plat, "s": shop_id, "o": ext_order_no},
                )
            )
            .mappings()
            .first()
        )

        if row is None:
            raise HTTPException(404, "order not found")

        order_id = int(row["id"])
        cur_wid = row.get("warehouse_id")

        if cur_wid is not None:
            return DevEnsureWarehouseOut(
                ok=True,
                order_id=order_id,
                platform=plat,
                shop_id=shop_id,
                ext_order_no=ext_order_no,
                warehouse_id=cur_wid,
                source="order",
                message="order already has warehouse_id",
            )

        # 解析店铺
        store_row = (
            (
                await session.execute(
                    text(
                        """
                    SELECT id FROM stores
                     WHERE platform=:p
                       AND shop_id=:s
                     LIMIT 1
                    """
                    ),
                    {"p": plat, "s": shop_id},
                )
            )
            .mappings()
            .first()
        )

        if store_row is None:
            raise HTTPException(404, "请先在【店铺管理】建立该店铺并绑定仓库")

        store_id = int(store_row["id"])

        # 解析仓库
        wid = await StoreService.resolve_default_warehouse(session, store_id=store_id)
        if wid is None:
            raise HTTPException(409, "无法解析仓库，请在店铺详情中绑定默认仓库")

        await session.execute(
            text(
                """
                UPDATE orders
                   SET warehouse_id=:wid,
                       updated_at=NOW()
                 WHERE id=:oid
                """
            ),
            {"wid": wid, "oid": order_id},
        )
        await session.commit()

        return DevEnsureWarehouseOut(
            ok=True,
            order_id=order_id,
            platform=plat,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            store_id=store_id,
            warehouse_id=wid,
            source="store_binding",
            message="warehouse resolved via store binding",
        )
