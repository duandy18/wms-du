# app/api/routers/platform_orders_fact_repo.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def line_key_from_inputs(*, platform_sku_id: Optional[str], line_no: Optional[int]) -> Optional[str]:
    """
    与 platform_order_fact_service._line_key 对齐：
    - 有 PSKU：PSKU:{platform_sku_id}
    - 无 PSKU：NO_PSKU:{line_no}
    """
    p = (platform_sku_id or "").strip()
    if p:
        return f"PSKU:{p}"
    if line_no is None:
        return None
    return f"NO_PSKU:{int(line_no)}"


async def load_shop_id_by_store_id(session: AsyncSession, *, store_id: int) -> str:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT shop_id
                      FROM stores
                     WHERE id = :id
                     LIMIT 1
                    """
                ),
                {"id": int(store_id)},
            )
        )
        .mappings()
        .first()
    )
    shop = (row.get("shop_id") if row else None) if row is not None else None
    if not shop:
        raise LookupError(f"store not found: store_id={store_id}")
    return str(shop)


async def load_fact_lines_for_order(
    session: AsyncSession,
    *,
    platform: str,
    store_id: int,
    ext_order_no: str,
) -> List[Dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT
                    line_no,
                    line_key,
                    platform_sku_id,
                    qty,
                    title,
                    spec,
                    extras
                  FROM platform_order_lines
                 WHERE platform = :platform
                   AND store_id = :store_id
                   AND ext_order_no = :ext_order_no
                 ORDER BY line_no ASC
                """
            ),
            {"platform": str(platform), "store_id": int(store_id), "ext_order_no": str(ext_order_no)},
        )
    ).mappings().all()

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "line_no": int(r.get("line_no") or 0),
                "line_key": str(r.get("line_key") or ""),
                "platform_sku_id": (r.get("platform_sku_id") or None),
                "qty": int(r.get("qty") or 1),
                "title": r.get("title"),
                "spec": r.get("spec"),
                "extras": r.get("extras"),
            }
        )
    return out
