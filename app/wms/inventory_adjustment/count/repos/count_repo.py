from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.shared.services.lot_code_contract import fetch_item_expiry_policy_map


class CountRepo:
    async def get_item_expiry_policy_text(
        self,
        session: AsyncSession,
        *,
        item_id: int,
    ) -> str:
        policy_map = await fetch_item_expiry_policy_map(session, {int(item_id)})
        if int(item_id) not in policy_map:
            raise LookupError(f"unknown item_id: {item_id}")
        return str(policy_map[int(item_id)])

    async def get_current_qty_by_lot_code(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        warehouse_id: int,
        lot_code: str | None,
    ) -> int:
        row = await session.execute(
            text(
                """
                SELECT COALESCE(SUM(s.qty), 0)
                  FROM stocks_lot s
                  LEFT JOIN lots lo ON lo.id = s.lot_id
                 WHERE s.item_id = :i
                   AND s.warehouse_id = :w
                   AND lo.lot_code IS NOT DISTINCT FROM CAST(:c AS TEXT)
                """
            ),
            {
                "i": int(item_id),
                "w": int(warehouse_id),
                "c": lot_code,
            },
        )
        return int(row.scalar() or 0)
