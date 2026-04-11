from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _norm_text(v: str | None) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


async def list_active_warehouses(
    session: AsyncSession,
    *,
    active_only: bool,
) -> list[dict[str, Any]]:
    where_sql = "WHERE w.active = TRUE" if active_only else ""
    sql = text(
        f"""
        SELECT
            w.id,
            w.name,
            w.code,
            w.active
        FROM warehouses AS w
        {where_sql}
        ORDER BY w.id ASC
        """
    )
    rows = (await session.execute(sql)).mappings().all()
    return [dict(r) for r in rows]


async def list_public_items(
    session: AsyncSession,
    *,
    q: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    cond = ["i.enabled = TRUE"]
    params: dict[str, Any] = {"limit": int(limit)}

    q_norm = _norm_text(q)
    if q_norm is not None:
        cond.append("(i.name ILIKE :q OR i.sku ILIKE :q)")
        params["q"] = f"%{q_norm}%"

    sql = text(
        f"""
        SELECT
            i.id,
            i.sku,
            i.name
        FROM items AS i
        WHERE {" AND ".join(cond)}
        ORDER BY i.name ASC, i.id ASC
        LIMIT :limit
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    return [dict(r) for r in rows]


__all__ = [
    "list_active_warehouses",
    "list_public_items",
]
