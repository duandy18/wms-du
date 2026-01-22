# app/api/routers/orders_fulfillment_debug_routes.py
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.orders_fulfillment_debug_schemas import (
    FULFILLMENT_DEBUG_VERSION,
    FulfillmentDebugAddress,
    FulfillmentDebugOut,
    FulfillmentServiceDebug,
)

_get_db = get_session
router = APIRouter(tags=["orders"])


async def _load_order_address(session: AsyncSession, order_id: int) -> FulfillmentDebugAddress:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  province,
                  city,
                  district,
                  detail
                FROM order_address
                WHERE order_id = :oid
                LIMIT 1
                """
            ),
            {"oid": int(order_id)},
        )
    ).mappings().first()

    if not row:
        return FulfillmentDebugAddress()

    return FulfillmentDebugAddress(
        province=(str(row.get("province") or "").strip() or None),
        city=(str(row.get("city") or "").strip() or None),
        district=(str(row.get("district") or "").strip() or None),
        detail=(str(row.get("detail") or "").strip() or None),
    )


async def _service_city_hit(
    session: AsyncSession,
    *,
    province: Optional[str],
    city: Optional[str],
) -> FulfillmentServiceDebug:
    prov = (province or "").strip() or None
    city_code = (city or "").strip() or None

    if not city_code:
        return FulfillmentServiceDebug(
            province_code=prov,
            city_code=None,
            hit=False,
            service_warehouse_id=None,
            reason="CITY_MISSING",
        )

    row = (
        await session.execute(
            text(
                """
                SELECT warehouse_id, province_code
                  FROM warehouse_service_cities
                 WHERE city_code = :c
                 LIMIT 1
                """
            ),
            {"c": city_code},
        )
    ).first()

    if not row:
        return FulfillmentServiceDebug(
            province_code=prov,
            city_code=city_code,
            hit=False,
            service_warehouse_id=None,
            reason="NO_SERVICE_WAREHOUSE",
        )

    wid = int(row[0]) if row[0] is not None else None
    prov_code = str(row[1] or "").strip() or prov

    if not (wid and wid > 0):
        return FulfillmentServiceDebug(
            province_code=prov_code or None,
            city_code=city_code,
            hit=False,
            service_warehouse_id=None,
            reason="NO_SERVICE_WAREHOUSE",
        )

    return FulfillmentServiceDebug(
        province_code=prov_code or None,
        city_code=city_code,
        hit=True,
        service_warehouse_id=int(wid),
        reason="OK",
    )


@router.get("/orders/{order_id}/fulfillment-debug", response_model=FulfillmentDebugOut)
async def get_fulfillment_debug(
    order_id: int = Path(..., ge=1),
    session: AsyncSession = Depends(_get_db),
) -> FulfillmentDebugOut:
    # 只取 identity（不取任何状态字段）
    row = (
        await session.execute(
            text(
                """
                SELECT
                  id,
                  platform,
                  shop_id,
                  ext_order_no
                FROM orders
                WHERE id = :oid
                LIMIT 1
                """
            ),
            {"oid": int(order_id)},
        )
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="order not found")

    plat = str(row.get("platform") or "").upper().strip()
    shop_id = str(row.get("shop_id") or "").strip()
    ext_order_no = (str(row.get("ext_order_no") or "").strip() or None)

    addr = await _load_order_address(session, int(order_id))
    service_dbg = await _service_city_hit(session, province=addr.province, city=addr.city)

    summary: Dict[str, Any] = {
        "service_city_hit": bool(service_dbg.hit),
        "service_warehouse_id": service_dbg.service_warehouse_id,
    }

    # ✅ 强制写死 version，彻底消灭“v1.1 幽灵”
    return FulfillmentDebugOut(
        version=FULFILLMENT_DEBUG_VERSION,
        order_id=int(row["id"]),
        platform=plat,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        address=addr,
        service=service_dbg,
        summary=summary,
    )
