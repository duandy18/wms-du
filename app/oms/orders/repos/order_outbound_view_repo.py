# app/oms/orders/repos/order_outbound_view_repo.py
from __future__ import annotations

from typing import Any, Dict, List, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def load_order_outbound_head(
    session: AsyncSession,
    *,
    order_id: int,
) -> Mapping[str, Any]:
    """
    订单出库页：读取订单头（来源真相 = orders）

    说明：
    - 这里只查真实 orders 表
    - 不掺 order_fulfillment / platform mirror / facts 聚合
    """
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                      id,
                      platform,
                      shop_id,
                      ext_order_no,
                      status,
                      created_at,
                      updated_at,
                      buyer_name,
                      buyer_phone,
                      order_amount,
                      pay_amount
                    FROM orders
                    WHERE id = :oid
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
    return row


async def load_order_outbound_lines(
    session: AsyncSession,
    *,
    order_id: int,
) -> List[Dict[str, Any]]:
    """
    订单出库页：读取订单行（来源真相 = order_lines）

    说明：
    - 当前只返回真实 order_lines 稳定字段
    - 不脑补商品名 / 规格 / 单位
    """
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                      id,
                      order_id,
                      item_id,
                      req_qty
                    FROM order_lines
                    WHERE order_id = :oid
                    ORDER BY id ASC
                    """
                ),
                {"oid": int(order_id)},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]
