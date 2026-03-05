# app/services/pick_task_loaders.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pick_task import PickTask


async def load_task(
    session: AsyncSession,
    task_id: int,
    *,
    for_update: bool = False,
) -> PickTask:
    stmt = select(PickTask).options(selectinload(PickTask.lines)).where(PickTask.id == task_id)
    if for_update:
        stmt = stmt.with_for_update()

    res = await session.execute(stmt)
    task = res.scalars().first()
    if task is None:
        raise ValueError(f"PickTask not found: id={task_id}")
    if task.lines:
        task.lines.sort(key=lambda line: (line.id,))
    return task


async def load_order_head(
    session: AsyncSession,
    order_id: int,
) -> Optional[Dict[str, Any]]:
    """
    一步到位迁移后：
    - orders 只承载订单头（platform/shop/ext/trace）
    - 执行仓/服务仓/履约状态在 order_fulfillment

    兼容输出字段：
    - warehouse_id：这里返回执行仓（actual_warehouse_id）
    - service_warehouse_id：返回计划/归属仓（planned_warehouse_id）
    - fulfillment_status：返回履约状态
    """
    row = (
        (
            await session.execute(
                SA(
                    """
                SELECT
                    o.id,
                    o.platform,
                    o.shop_id,
                    o.ext_order_no,
                    f.actual_warehouse_id AS warehouse_id,
                    f.planned_warehouse_id AS service_warehouse_id,
                    f.fulfillment_status AS fulfillment_status,
                    o.trace_id
                  FROM orders o
                  LEFT JOIN order_fulfillment f ON f.order_id = o.id
                 WHERE o.id = :oid
                 LIMIT 1
                """
                ),
                {"oid": order_id},
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


async def load_order_items(
    session: AsyncSession,
    order_id: int,
) -> List[Dict[str, Any]]:
    rows = (
        (
            await session.execute(
                SA(
                    """
                SELECT
                    id,
                    item_id,
                    COALESCE(qty, 0) AS qty
                  FROM order_items
                 WHERE order_id = :oid
                 ORDER BY id ASC
                """
                ),
                {"oid": order_id},
            )
        )
        .mappings()
        .all()
    )

    return [
        {
            "order_line_id": int(r["id"]),
            "item_id": int(r["item_id"]),
            "qty": int(r["qty"] or 0),
        }
        for r in rows
    ]
