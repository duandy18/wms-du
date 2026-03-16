# app/tms/shipment/router_helpers.py
# 分拆说明：
# - 本文件承载 Shipment 路由共享 helper；
# - 当前只保留订单定位与 trace_id 解析能力；
# - 供 orders_fulfillment_v2 下的 Shipment / Reserve / Pick 相关路由复用。
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_service import OrderService


async def get_order_ref_and_trace_id(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
) -> tuple[str, Optional[str]]:
    plat = platform.upper()
    order_ref = f"ORD:{plat}:{shop_id}:{ext_order_no}"

    trace_id: Optional[str] = None

    try:
        trace_id = await OrderService.get_trace_id_for_order(
            session=session,
            platform=plat,
            shop_id=shop_id,
            ref=order_ref,
        )
    except Exception:
        trace_id = None

    if not trace_id:
        row = (
            (
                await session.execute(
                    text(
                        """
                    SELECT trace_id
                      FROM orders
                     WHERE platform = :p
                       AND shop_id  = :s
                       AND ext_order_no = :o
                     ORDER BY id DESC
                     LIMIT 1
                    """
                    ),
                    {"p": plat, "s": shop_id, "o": ext_order_no},
                )
            )
            .mappings()
            .first()
        )
        if row:
            trace_id = row.get("trace_id")

    return order_ref, trace_id
