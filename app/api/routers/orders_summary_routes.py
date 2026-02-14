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

    # ✅ store_id（stores.id）：用于内部治理/解析卡 replay 入参（前端不得推导）
    store_id: Optional[int] = None

    # 执行仓（实际出库）
    warehouse_id: Optional[int] = None
    # 服务仓（系统裁决、服务归属）
    service_warehouse_id: Optional[int] = None
    # 履约状态（系统事实）
    fulfillment_status: Optional[str] = None

    # 派生字段（审计/统计；前端可不展示）
    warehouse_assign_mode: Optional[str] = None

    # ✅ 后端对齐的可操作事实（前端不得推导）
    can_manual_assign_execution_warehouse: bool = False
    manual_assign_hint: Optional[str] = None

    order_amount: Optional[float] = None
    pay_amount: Optional[float] = None


class OrdersSummaryResponse(BaseModel):
    ok: bool = True
    data: List[OrderSummaryOut]
    # ✅ 候选执行仓（后端给出，前端不得自行拉 /warehouses）
    warehouses: List[WarehouseOptionOut]


def _derive_assign_mode(
    *,
    fulfillment_status: Optional[str],
    warehouse_id: Optional[int],
    service_warehouse_id: Optional[int],
) -> str:
    """
    说明：这里的 warehouse_id/service_warehouse_id 都是“兼容字段名”，实际来源是：
      - service_warehouse_id := order_fulfillment.planned_warehouse_id
      - warehouse_id := order_fulfillment.actual_warehouse_id
    """
    fs = (fulfillment_status or "").strip().upper()
    if fs == "MANUALLY_ASSIGNED":
        return "MANUAL"
    if fs == "READY_TO_FULFILL" and warehouse_id is not None and service_warehouse_id is not None:
        if int(warehouse_id) == int(service_warehouse_id):
            return "AUTO_FROM_SERVICE"
        return "OTHER"

    # ✅ 有 planned（服务仓）但没有 actual（执行仓）：已分配服务仓，待指定执行仓
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
    time_from: Optional[datetime],
    time_to: Optional[datetime],
    limit: int,
) -> List[Mapping[str, Any]]:
    """
    一步到位迁移后：
    - orders 只保留订单头
    - 履约/仓库快照在 order_fulfillment
    因此这里从 orders LEFT JOIN order_fulfillment 取 planned/actual/status。

    参数语义（不兼容硬改）：
    - status：过滤 orders.status（CREATED / PICKABLE / ...）
    - fulfillment_status：过滤 order_fulfillment.fulfillment_status（SERVICE_ASSIGNED / READY_TO_FULFILL / ...）

    ✅ PROD-only（简化口径）：
    - 排除测试店铺（platform_test_shops.code='DEFAULT'，以 store_id 为事实锚点）
    """
    clauses: List[str] = []
    params: Dict[str, Any] = {"limit": limit}

    p = _norm_optional_str(platform)
    s = _norm_optional_str(shop_id)
    st = _norm_optional_str(status)
    fst = _norm_optional_str(fulfillment_status)

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
        clauses.append("f.fulfillment_status = :fst")
        params["fst"] = fst.strip().upper()

    if time_from:
        clauses.append("o.created_at >= :from_ts")
        params["from_ts"] = time_from
    if time_to:
        clauses.append("o.created_at <= :to_ts")
        params["to_ts"] = time_to

    # PROD-only：测试店铺门禁（store_id）
    clauses.append(
        """
        NOT EXISTS (
          SELECT 1
            FROM stores ss
            JOIN platform_test_shops pts
              ON pts.store_id = ss.id
             AND pts.code = 'DEFAULT'
           WHERE upper(ss.platform) = upper(o.platform)
             AND btrim(CAST(ss.shop_id AS text)) = btrim(CAST(o.shop_id AS text))
        )
        """.strip()
    )

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
    # 这里故意做得保守：给出 active != false 的仓作为候选集合
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
        status: Optional[str] = Query(None, description="订单头状态（orders.status）：CREATED / PICKABLE / ..."),
        fulfillment_status: Optional[str] = Query(
            None, description="履约状态（order_fulfillment.fulfillment_status）：SERVICE_ASSIGNED / READY_TO_FULFILL / ..."
        ),
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
            time_from=time_from,
            time_to=time_to,
            limit=limit,
        )

        warehouses = await _list_candidate_warehouses(session)

        data: List[OrderSummaryOut] = []
        for r in rows:
            fs = str(r.get("fulfillment_status") or "").strip().upper()
            whid = r.get("warehouse_id")
            swid = r.get("service_warehouse_id")
            sid = r.get("store_id")

            # ✅ 可操作事实：SERVICE_ASSIGNED 且已有 planned 且 actual 为空
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
                    store_id=int(sid) if sid is not None else None,
                    warehouse_id=int(whid) if whid is not None else None,
                    service_warehouse_id=int(swid) if swid is not None else None,
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

        return OrdersSummaryResponse(ok=True, data=data, warehouses=warehouses)
