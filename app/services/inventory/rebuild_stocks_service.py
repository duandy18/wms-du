# app/services/inventory/rebuild_stocks_service.py
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class RebuildService:
    @staticmethod
    async def rebuild_stocks_lot(
        session: AsyncSession,
        *,
        time_from: Optional[str] = None,
        time_to: Optional[str] = None,
    ) -> Dict[str, Any]:

        await session.execute(text("TRUNCATE TABLE stocks_lot RESTART IDENTITY"))

        where_sql = ""
        params: Dict[str, Any] = {}
        conds = []
        if time_from:
            conds.append("occurred_at >= :time_from")
            params["time_from"] = time_from
        if time_to:
            conds.append("occurred_at <= :time_to")
            params["time_to"] = time_to
        if conds:
            where_sql = "WHERE " + " AND ".join(conds)

        insert_sql = f"""
            INSERT INTO stocks_lot (warehouse_id, item_id, lot_id, qty)
            SELECT
                warehouse_id,
                item_id,
                lot_id,
                SUM(delta) AS qty
            FROM stock_ledger
            {where_sql}
            GROUP BY warehouse_id, item_id, lot_id
            HAVING SUM(delta) != 0;
        """

        await session.execute(text(insert_sql), params)

        summary_sql = """
            SELECT COUNT(*) AS slot_count,
                   COALESCE(SUM(qty), 0) AS total_qty
            FROM stocks_lot
        """
        summary = (await session.execute(text(summary_sql))).mappings().first()

        return {
            "slot_count": int(summary["slot_count"]),
            "total_qty": int(summary["total_qty"]),
        }
