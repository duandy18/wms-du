# app/services/order_ingest_routing/order_address_repo.py
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def load_order_address(session: AsyncSession, *, order_id: int) -> Optional[Dict[str, str]]:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT province, city, district, detail
                      FROM order_address
                     WHERE order_id = :oid
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
        return None

    def _s(x: Any) -> str:
        return str(x).strip() if x is not None else ""

    out: Dict[str, str] = {}
    for k in ("province", "city", "district", "detail"):
        v = _s(row.get(k))
        if v:
            out[k] = v
    return out or None
