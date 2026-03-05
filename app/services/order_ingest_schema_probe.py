# app/services/order_ingest_schema_probe.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def has_column(session: AsyncSession, *, table_name: str, column_name: str) -> bool:
    row = (
        await session.execute(
            text(
                """
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_schema='public'
                   AND table_name=:t
                   AND column_name=:c
                """
            ),
            {"t": table_name, "c": column_name},
        )
    ).first()
    return bool(row)


async def orders_has_extras(session: AsyncSession) -> bool:
    return await has_column(session, table_name="orders", column_name="extras")


async def order_items_has_extras(session: AsyncSession) -> bool:
    return await has_column(session, table_name="order_items", column_name="extras")


async def orders_has_warehouse_id(session: AsyncSession) -> bool:
    """
    已废弃：Route C / routing 不再写 orders.warehouse_id（也不再需要探测该列是否存在）。

    ✅ 新主线：
      - 仓库归属快照写入 order_fulfillment（planned_warehouse_id / actual_warehouse_id / fulfillment_status / ...）

    ❌ 禁止回潮：
      - ingest 阶段根据 schema 探测分支写 orders.warehouse_id
    """
    raise RuntimeError(
        "orders_has_warehouse_id 已废弃：routing 不再写 orders.warehouse_id，"
        "仓库归属写入 order_fulfillment(planned/actual)。"
    )
