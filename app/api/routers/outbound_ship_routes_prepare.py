# app/api/routers/outbound_ship_routes_prepare.py
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.routers.outbound_ship_schemas import (
    ShipPrepareItem,
    ShipPrepareRequest,
    ShipPrepareResponse,
)


def register(router: APIRouter) -> None:
    @router.post("/ship/prepare-from-order", response_model=ShipPrepareResponse)
    async def prepare_from_order(
        payload: ShipPrepareRequest,
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> ShipPrepareResponse:
        """
        根据平台订单信息预取发货所需基础数据：

        - order_id
        - 收货地址（省/市/区/详细地址 + 姓名/电话）
        - 行项目 item_id + qty
        - total_qty
        - weight_kg：基于 item.weight_kg 的预估总重量（不含包材）
        - trace_id：订单 trace_id（供 /ship/confirm 使用）
        """
        plat = payload.platform.upper()
        shop_id = payload.shop_id
        ext_order_no = payload.ext_order_no

        sql = text(
            """
            SELECT
              o.id AS order_id,
              o.platform,
              o.shop_id,
              o.ext_order_no,
              o.trace_id,
              addr.province,
              addr.city,
              addr.district,
              addr.receiver_name,
              addr.receiver_phone,
              addr.detail AS address_detail,
              COALESCE(SUM(COALESCE(oi.qty, 0)), 0) AS total_qty,
              COALESCE(
                SUM(
                  COALESCE(oi.qty, 0) * COALESCE(it.weight_kg, 0)
                ),
                0
              ) AS estimated_weight_kg,
              COALESCE(
                json_agg(
                  json_build_object(
                    'item_id', oi.item_id,
                    'qty', COALESCE(oi.qty, 0)
                  )
                ) FILTER (WHERE oi.id IS NOT NULL),
                '[]'::json
              ) AS items
            FROM orders AS o
            LEFT JOIN order_address AS addr ON addr.order_id = o.id
            LEFT JOIN order_items AS oi ON oi.order_id = o.id
            LEFT JOIN items AS it ON it.id = oi.item_id
            WHERE o.platform = :platform
              AND o.shop_id = :shop_id
              AND o.ext_order_no = :ext_order_no
            GROUP BY
              o.id, o.platform, o.shop_id, o.ext_order_no,
              o.trace_id,
              addr.province, addr.city, addr.district,
              addr.receiver_name, addr.receiver_phone, addr.detail
            LIMIT 1
            """
        )

        row = (
            (
                await session.execute(
                    sql,
                    {
                        "platform": plat,
                        "shop_id": shop_id,
                        "ext_order_no": ext_order_no,
                    },
                )
            )
            .mappings()
            .first()
        )

        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order not found")

        order_id = int(row["order_id"])
        province = row.get("province")
        city = row.get("city")
        district = row.get("district")
        receiver_name = row.get("receiver_name")
        receiver_phone = row.get("receiver_phone")
        address_detail = row.get("address_detail")

        total_qty = int(row["total_qty"] or 0)
        items_raw = row.get("items") or []
        items = [
            ShipPrepareItem(item_id=int(it["item_id"]), qty=int(it["qty"])) for it in items_raw
        ]

        est_weight = float(row.get("estimated_weight_kg") or 0.0)
        weight_kg: Optional[float] = est_weight if est_weight > 0 else None

        trace_id = row.get("trace_id")
        ref = f"ORD:{plat}:{shop_id}:{ext_order_no}"

        return ShipPrepareResponse(
            ok=True,
            order_id=order_id,
            platform=plat,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            ref=ref,
            province=province,
            city=city,
            district=district,
            receiver_name=receiver_name,
            receiver_phone=receiver_phone,
            address_detail=address_detail,
            items=items,
            total_qty=total_qty,
            weight_kg=weight_kg,
            trace_id=trace_id,
        )
