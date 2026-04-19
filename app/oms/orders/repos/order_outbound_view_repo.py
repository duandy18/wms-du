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
    订单出库页：读取订单行（来源真相 = order_lines + item display）

    说明：
    - 核心真相是 order_lines
    - 为作业页补充商品展示字段：sku / name / spec / base_uom
    - 单位优先取 base_uom；若异常缺失，则退回该商品第一条 item_uom
    """
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                      ol.id,
                      ol.order_id,
                      ol.item_id,
                      ol.req_qty,
                      i.sku AS item_sku,
                      i.name AS item_name,
                      i.spec AS item_spec,
                      u.base_uom_id,
                      u.base_uom_name
                    FROM order_lines ol
                    JOIN items i
                      ON i.id = ol.item_id
                    LEFT JOIN LATERAL (
                      SELECT
                        iu.id AS base_uom_id,
                        COALESCE(NULLIF(BTRIM(iu.display_name), ''), iu.uom) AS base_uom_name
                      FROM item_uoms iu
                      WHERE iu.item_id = ol.item_id
                      ORDER BY
                        CASE WHEN iu.is_base THEN 0 ELSE 1 END,
                        iu.id ASC
                      LIMIT 1
                    ) u ON TRUE
                    WHERE ol.order_id = :oid
                    ORDER BY ol.id ASC
                    """
                ),
                {"oid": int(order_id)},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]
