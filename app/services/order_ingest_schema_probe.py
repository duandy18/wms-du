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
    return await has_column(session, table_name="orders", column_name="warehouse_id")
