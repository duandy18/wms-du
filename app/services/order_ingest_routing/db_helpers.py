# app/services/order_ingest_routing/db_helpers.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import ProgrammingError


async def table_exists(session: AsyncSession, table_name: str) -> bool:
    """
    兼容：测试库/迁移未跑时，相关表可能不存在。
    使用 to_regclass 避免直接查询触发 UndefinedTable。
    """
    try:
        row = await session.execute(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": table_name})
        return bool(row.scalar() or False)
    except Exception:
        return False


async def resolve_service_warehouse_by_province(session: AsyncSession, *, province: str) -> Optional[int]:
    """
    省级默认：按省命中唯一服务仓（互斥）
    - 依赖 warehouse_service_provinces.province_code 全局唯一（互斥）
    """
    row = await session.execute(
        text(
            """
            SELECT warehouse_id
              FROM warehouse_service_provinces
             WHERE province_code = :p
             LIMIT 1
            """
        ),
        {"p": province},
    )
    rec = row.first()
    if rec is None or rec[0] is None:
        return None
    return int(rec[0])


async def resolve_service_warehouse_by_city(session: AsyncSession, *, city: str) -> Optional[int]:
    """
    城市例外：按市命中唯一服务仓（互斥）
    - 依赖 warehouse_service_cities.city_code 全局唯一（互斥）
    """
    row = await session.execute(
        text(
            """
            SELECT warehouse_id
              FROM warehouse_service_cities
             WHERE city_code = :c
             LIMIT 1
            """
        ),
        {"c": city},
    )
    rec = row.first()
    if rec is None or rec[0] is None:
        return None
    return int(rec[0])


async def is_city_split_province(session: AsyncSession, *, province: str) -> bool:
    """
    判断该省是否启用“按城市配置”（省级冻结）。
    若表不存在（测试库未迁移），视为未启用。
    """
    if not await table_exists(session, "warehouse_service_city_split_provinces"):
        return False

    try:
        row = await session.execute(
            text(
                """
                SELECT 1
                  FROM warehouse_service_city_split_provinces
                 WHERE province_code = :p
                 LIMIT 1
                """
            ),
            {"p": province},
        )
        return row.first() is not None
    except ProgrammingError:
        # 兼容：表不存在等异常时，视为未启用
        return False
