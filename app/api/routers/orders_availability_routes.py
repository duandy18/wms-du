# app/api/routers/orders_availability_routes.py
from __future__ import annotations

from typing import List, Optional

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.services.order_warehouse_availability import OrderWarehouseAvailabilityService


class AvailabilityLineOut(BaseModel):
    item_id: int
    req_qty: int
    sku_id: Optional[str] = None
    title: Optional[str] = None


class AvailabilityCellOut(BaseModel):
    warehouse_id: int
    item_id: int
    available: int
    shortage: int
    status: str  # ENOUGH | SHORTAGE


class WarehouseBriefOut(BaseModel):
    id: int
    code: Optional[str] = None
    name: Optional[str] = None


class OrderWarehouseAvailabilityResponse(BaseModel):
    ok: bool = True
    order_id: int
    # ✅ Explain 输出范围说明：
    # - DEFAULT_SERVICE_EXECUTION：未传 warehouse_ids，后端默认仅返回 service/execution（护栏）
    # - EXPLICIT_WAREHOUSE_IDS：前端显式传入 warehouse_ids（用于候选仓对照）
    scope: str
    warehouses: List[WarehouseBriefOut]
    lines: List[AvailabilityLineOut]
    matrix: List[AvailabilityCellOut]


def _parse_ids(csv: Optional[str]) -> List[int]:
    if not csv:
        return []
    out: List[int] = []
    seen: set[int] = set()
    for part in str(csv).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            v = int(part)
        except Exception:
            continue
        if v <= 0 or v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


async def _load_order_head(session: AsyncSession, *, order_id: int) -> dict:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                      o.id,
                      o.platform,
                      o.shop_id,
                      f.planned_warehouse_id AS service_warehouse_id,
                      f.actual_warehouse_id  AS warehouse_id
                    FROM orders o
                    LEFT JOIN order_fulfillment f ON f.order_id = o.id
                    WHERE o.id = :oid
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
        raise ValueError(f"order not found: id={order_id}")
    return {
        "id": int(row["id"]),
        "platform": str(row["platform"]),
        "shop_id": str(row["shop_id"]),
        "service_warehouse_id": int(row["service_warehouse_id"]) if row.get("service_warehouse_id") is not None else None,
        "warehouse_id": int(row["warehouse_id"]) if row.get("warehouse_id") is not None else None,
    }


async def _load_warehouses_brief(session: AsyncSession, *, warehouse_ids: List[int]) -> List[WarehouseBriefOut]:
    if not warehouse_ids:
        return []
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT id, code, name
                    FROM warehouses
                    WHERE id = ANY(:ids)
                    ORDER BY id
                    """
                ),
                {"ids": [int(x) for x in warehouse_ids]},
            )
        )
        .mappings()
        .all()
    )
    out: List[WarehouseBriefOut] = []
    for r in rows:
        out.append(
            WarehouseBriefOut(
                id=int(r["id"]),
                code=str(r["code"]) if r.get("code") is not None else None,
                name=str(r["name"]) if r.get("name") is not None else None,
            )
        )
    return out


def register(router) -> None:
    @router.get("/orders/{order_id}/warehouse-availability", response_model=OrderWarehouseAvailabilityResponse)
    async def order_warehouse_availability(
        order_id: int,
        session: AsyncSession = Depends(get_session),
        warehouse_ids: Optional[str] = Query(None, description="逗号分隔的 warehouse_id 列表"),
    ) -> OrderWarehouseAvailabilityResponse:
        head = await _load_order_head(session, order_id=order_id)

        wh_ids = _parse_ids(warehouse_ids)
        scope = "EXPLICIT_WAREHOUSE_IDS" if wh_ids else "DEFAULT_SERVICE_EXECUTION"

        if not wh_ids:
            # 默认只给“当前事实相关仓”：service + execution
            for x in [head.get("service_warehouse_id"), head.get("warehouse_id")]:
                if x is None:
                    continue
                v = int(x)
                if v > 0 and v not in wh_ids:
                    wh_ids.append(v)

        warehouses = await _load_warehouses_brief(session, warehouse_ids=wh_ids)

        lines, matrix = await OrderWarehouseAvailabilityService.build_matrix(
            session,
            platform=head["platform"],
            shop_id=head["shop_id"],
            order_id=int(order_id),
            warehouse_ids=wh_ids,
        )

        return OrderWarehouseAvailabilityResponse(
            ok=True,
            order_id=int(order_id),
            scope=scope,
            warehouses=warehouses,
            lines=[AvailabilityLineOut(**x.to_dict()) for x in lines],
            matrix=[AvailabilityCellOut(**x.to_dict()) for x in matrix],
        )
