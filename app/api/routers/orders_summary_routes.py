# app/api/routers/orders_summary_routes.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session


class OrderSummaryOut(BaseModel):
    id: int
    platform: str
    shop_id: str
    ext_order_no: str
    status: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    warehouse_id: Optional[int] = None
    service_warehouse_id: Optional[int] = None
    fulfillment_status: Optional[str] = None

    warehouse_assign_mode: Optional[str] = None

    # ✅ 后端对齐的可操作事实（前端不得推导）
    can_manual_assign_execution_warehouse: bool = False
    manual_assign_hint: Optional[str] = None

    order_amount: Optional[float] = None
    pay_amount: Optional[float] = None


class OrdersSummaryResponse(BaseModel):
    ok: bool = True
    data: List[OrderSummaryOut]


def _derive_assign_mode(
    *,
    fulfillment_status: Optional[str],
    warehouse_id: Optional[int],
    service_warehouse_id: Optional[int],
) -> str:
    fs = (fulfillment_status or "").strip().upper()
    if fs == "MANUALLY_ASSIGNED":
        return "MANUAL"
    if fs == "READY_TO_FULFILL" and warehouse_id is not None and service_warehouse_id is not None:
        if int(warehouse_id) == int(service_warehouse_id):
            return "AUTO_FROM_SERVICE"
        return "OTHER"
    if warehouse_id is None:
        return "UNASSIGNED"
    return "OTHER"


async def _list_orders_summary_rows(
    session: AsyncSession,
    *,
    platform: Optional[str],
    shop_id: Optional[str],
    status: Optional[str],
    time_from: Optional[datetime],
    time_to: Optional[datetime],
    limit: int,
) -> List[Mapping[str, Any]]:
    clauses: List[str] = []
    params: Dict[str, Any] = {"limit": limit}

    if platform:
        clauses.append("platform = :p")
        params["p"] = platform.upper()
    if shop_id:
        clauses.append("shop_id = :s")
        params["s"] = shop_id
    if status:
        clauses.append("status = :st")
        params["st"] = status
    if time_from:
        clauses.append("created_at >= :from_ts")
        params["from_ts"] = time_from
    if time_to:
        clauses.append("created_at <= :to_ts")
        params["to_ts"] = time_to

    where_sql = ""
    if clauses:
        where_sql = "WHERE " + " AND ".join(clauses)

    rows = (
        (
            await session.execute(
                text(
                    f"""
                    SELECT
                        id,
                        platform,
                        shop_id,
                        ext_order_no,
                        status,
                        created_at,
                        updated_at,
                        warehouse_id,
                        service_warehouse_id,
                        fulfillment_status,
                        order_amount,
                        pay_amount
                      FROM orders
                      {where_sql}
                     ORDER BY created_at DESC, id DESC
                     LIMIT :limit
                    """
                ),
                params,
            )
        )
        .mappings()
        .all()
    )
    return rows


def register(router) -> None:
    @router.get("/orders/summary", response_model=OrdersSummaryResponse)
    async def orders_summary(
        session: AsyncSession = Depends(get_session),
        platform: Optional[str] = Query(None),
        shop_id: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
        time_from: Optional[datetime] = Query(None),
        time_to: Optional[datetime] = Query(None),
        limit: int = Query(100),
    ) -> OrdersSummaryResponse:
        rows = await _list_orders_summary_rows(
            session,
            platform=platform,
            shop_id=shop_id,
            status=status,
            time_from=time_from,
            time_to=time_to,
            limit=limit,
        )

        data: List[OrderSummaryOut] = []
        for r in rows:
            fs = str(r.get("fulfillment_status") or "").strip().upper()
            whid = r.get("warehouse_id")
            swid = r.get("service_warehouse_id")

            can_manual = (fs == "SERVICE_ASSIGNED") and (swid is not None) and (whid is None)

            data.append(
                OrderSummaryOut(
                    id=r["id"],
                    platform=r["platform"],
                    shop_id=r["shop_id"],
                    ext_order_no=r["ext_order_no"],
                    status=r.get("status"),
                    created_at=r["created_at"],
                    updated_at=r.get("updated_at"),
                    warehouse_id=whid,
                    service_warehouse_id=swid,
                    fulfillment_status=r.get("fulfillment_status"),
                    warehouse_assign_mode=_derive_assign_mode(
                        fulfillment_status=r.get("fulfillment_status"),
                        warehouse_id=int(whid) if whid is not None else None,
                        service_warehouse_id=int(swid) if swid is not None else None,
                    ),
                    can_manual_assign_execution_warehouse=can_manual,
                    manual_assign_hint=("待指定执行仓" if can_manual else None),
                    order_amount=float(r["order_amount"]) if r.get("order_amount") else None,
                    pay_amount=float(r["pay_amount"]) if r.get("pay_amount") else None,
                )
            )

        return OrdersSummaryResponse(ok=True, data=data)
