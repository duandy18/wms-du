# app/api/routers/orders_summary_routes.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session


class WarehouseOptionOut(BaseModel):
    id: int
    code: Optional[str] = None
    name: Optional[str] = None
    active: Optional[bool] = None


class OrderSummaryOut(BaseModel):
    id: int
    platform: str
    shop_id: str
    ext_order_no: str
    status: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    # store 主键（stores.id）
    store_id: Optional[int] = None

    # 执行仓
    warehouse_id: Optional[int] = None
    # 服务仓
    service_warehouse_id: Optional[int] = None

    # ✅ 显式执行阶段真相（PICK / SHIP；NULL = 未进入执行链路）
    execution_stage: Optional[str] = None

    # ✅ 出库事实字段（路 A：替代 fulfillment_status 的 SHIP 子状态机）
    ship_committed_at: Optional[datetime] = None
    shipped_at: Optional[datetime] = None

    # ✅ 履约状态（降级字段）：仅路由/阻断/人工干预语义（禁止承载 SHIP_COMMITTED/SHIPPED）
    fulfillment_status: Optional[str] = None

    warehouse_assign_mode: Optional[str] = None

    can_manual_assign_execution_warehouse: bool = False
    manual_assign_hint: Optional[str] = None

    order_amount: Optional[float] = None
    pay_amount: Optional[float] = None


class OrdersSummaryResponse(BaseModel):
    ok: bool = True
    data: List[OrderSummaryOut]
    warehouses: List[WarehouseOptionOut]


def _derive_assign_mode(
    *,
    fulfillment_status: Optional[str],
    execution_stage: Optional[str],
    warehouse_id: Optional[int],
    service_warehouse_id: Optional[int],
) -> str:
    """
    Phase 5（去混合化）：assign_mode 只看事实字段，不再依赖 READY_TO_FULFILL 等“阶段味儿”状态。
    """
    stg = (execution_stage or "").strip().upper()

    # 彻底消除“预占/RESERVE”概念：历史若出现 RESERVE，一律视为 PICK（仅用于展示/推导）
    if stg == "RESERVE":
        stg = "PICK"

    if stg == "SHIP":
        return "SHIP"
    if stg == "PICK":
        return "PICK"

    fs = (fulfillment_status or "").strip().upper()
    if fs == "MANUALLY_ASSIGNED":
        return "MANUAL"

    # ✅ 未进入执行阶段时：只按仓事实推导
    if warehouse_id is None and service_warehouse_id is not None:
        return "SERVICE_ASSIGNED"
    if warehouse_id is None:
        return "UNASSIGNED"
    return "OTHER"


def _norm_optional_str(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


async def _list_orders_summary_rows(
    session: AsyncSession,
    *,
    platform: Optional[str],
    shop_id: Optional[str],
    status: Optional[str],
    fulfillment_status: Optional[str],
    execution_stage: Optional[str],
    time_from: Optional[datetime],
    time_to: Optional[datetime],
    limit: int,
) -> List[Mapping[str, Any]]:

    clauses: List[str] = []
    params: Dict[str, Any] = {"limit": limit}

    p = _norm_optional_str(platform)
    s = _norm_optional_str(shop_id)
    st = _norm_optional_str(status)
    fst = _norm_optional_str(fulfillment_status)
    estg = _norm_optional_str(execution_stage)

    if p:
        clauses.append("o.platform = :p")
        params["p"] = p.upper()

    if s:
        clauses.append("o.shop_id = :s")
        params["s"] = s

    if st:
        clauses.append("o.status = :st")
        params["st"] = st.strip().upper()

    if fst:
        # ✅ 注意：fulfillment_status 现在是“路由/阻断字段”，不再包含 SHIP_COMMITTED/SHIPPED
        clauses.append("f.fulfillment_status = :fst")
        params["fst"] = fst.strip().upper()

    if estg:
        # 对外只接受 PICK / SHIP；若传 RESERVE，当作 PICK（兼容输入，但不宣称）
        estg2 = estg.strip().upper()
        if estg2 == "RESERVE":
            estg2 = "PICK"
        clauses.append("f.execution_stage = :estg")
        params["estg"] = estg2

    if time_from:
        clauses.append("o.created_at >= :from_ts")
        params["from_ts"] = time_from

    if time_to:
        clauses.append("o.created_at <= :to_ts")
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
                        o.id,
                        o.platform,
                        o.shop_id,
                        o.ext_order_no,
                        o.status,
                        o.created_at,
                        o.updated_at,
                        s.id AS store_id,
                        f.actual_warehouse_id AS warehouse_id,
                        f.planned_warehouse_id AS service_warehouse_id,
                        f.execution_stage,
                        f.ship_committed_at,
                        f.shipped_at,
                        f.fulfillment_status,
                        o.order_amount,
                        o.pay_amount
                      FROM orders o
                      LEFT JOIN stores s
                        ON s.platform = o.platform
                       AND btrim(CAST(s.shop_id AS text)) = btrim(CAST(o.shop_id AS text))
                      LEFT JOIN order_fulfillment f ON f.order_id = o.id
                      {where_sql}
                     ORDER BY o.created_at DESC, o.id DESC
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


async def _list_candidate_warehouses(session: AsyncSession) -> List[WarehouseOptionOut]:
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT id, code, name, active
                      FROM warehouses
                     WHERE active IS DISTINCT FROM false
                     ORDER BY id ASC
                    """
                )
            )
        )
        .mappings()
        .all()
    )

    out: List[WarehouseOptionOut] = []
    for r in rows:
        out.append(
            WarehouseOptionOut(
                id=int(r["id"]),
                code=str(r["code"]) if r.get("code") is not None else None,
                name=str(r["name"]) if r.get("name") is not None else None,
                active=bool(r["active"]) if r.get("active") is not None else None,
            )
        )
    return out


def register(router) -> None:
    @router.get("/orders/summary", response_model=OrdersSummaryResponse)
    async def orders_summary(
        session: AsyncSession = Depends(get_session),
        platform: Optional[str] = Query(None),
        shop_id: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
        fulfillment_status: Optional[str] = Query(None, description="路由/阻断字段（非阶段）；如 SERVICE_ASSIGNED / FULFILLMENT_BLOCKED"),
        execution_stage: Optional[str] = Query(None, description="PICK / SHIP（NULL=未进入执行链路）"),
        time_from: Optional[datetime] = Query(None),
        time_to: Optional[datetime] = Query(None),
        limit: int = Query(100),
    ) -> OrdersSummaryResponse:

        rows = await _list_orders_summary_rows(
            session,
            platform=platform,
            shop_id=shop_id,
            status=status,
            fulfillment_status=fulfillment_status,
            execution_stage=execution_stage,
            time_from=time_from,
            time_to=time_to,
            limit=limit,
        )

        warehouses = await _list_candidate_warehouses(session)

        data: List[OrderSummaryOut] = []
        for r in rows:
            fs = str(r.get("fulfillment_status") or "").strip().upper()
            stg = str(r.get("execution_stage") or "").strip().upper()
            if stg == "RESERVE":
                stg = "PICK"

            whid = r.get("warehouse_id")
            swid = r.get("service_warehouse_id")
            sid = r.get("store_id")

            # 只有在“执行阶段未开始”且处于 SERVICE_ASSIGNED 时才允许手工指定执行仓
            can_manual = (stg == "") and (fs == "SERVICE_ASSIGNED") and (swid is not None) and (whid is None)

            data.append(
                OrderSummaryOut(
                    id=r["id"],
                    platform=r["platform"],
                    shop_id=r["shop_id"],
                    ext_order_no=r["ext_order_no"],
                    status=r.get("status"),
                    created_at=r["created_at"],
                    updated_at=r.get("updated_at"),
                    store_id=int(sid) if sid is not None else None,
                    warehouse_id=int(whid) if whid is not None else None,
                    service_warehouse_id=int(swid) if swid is not None else None,
                    execution_stage=r.get("execution_stage"),
                    ship_committed_at=r.get("ship_committed_at"),
                    shipped_at=r.get("shipped_at"),
                    fulfillment_status=r.get("fulfillment_status"),
                    warehouse_assign_mode=_derive_assign_mode(
                        fulfillment_status=r.get("fulfillment_status"),
                        execution_stage=r.get("execution_stage"),
                        warehouse_id=int(whid) if whid is not None else None,
                        service_warehouse_id=int(swid) if swid is not None else None,
                    ),
                    can_manual_assign_execution_warehouse=can_manual,
                    manual_assign_hint=("待指定执行仓" if can_manual else None),
                    order_amount=float(r["order_amount"]) if r.get("order_amount") else None,
                    pay_amount=float(r["pay_amount"]) if r.get("pay_amount") else None,
                )
            )

        return OrdersSummaryResponse(ok=True, data=data, warehouses=warehouses)
