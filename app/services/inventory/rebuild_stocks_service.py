# app/services/inventory/rebuild_stocks_service.py
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class RebuildService:
    """
    从 ledger 重算库存余额，用于审计 / 恢复 / 对账。

    Phase 4E（真收口）：
    - 主余额表：stocks_lot（lot-world）
    - 禁止重建/写入 legacy stocks（不允许双余额源）
    """

    @staticmethod
    async def rebuild_stocks(
        session: AsyncSession,
        *,
        time_from: Optional[str] = None,
        time_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Phase 4E：禁用。

        旧功能：从 ledger 重建 shadow batch-world（stocks）。
        现在不允许任何执行路径触碰 legacy stocks。
        """
        _ = session
        _ = time_from
        _ = time_to
        raise RuntimeError(
            "Phase 4E: rebuild_stocks(stocks batch-world) 已禁用。"
            "禁止写入/读取 legacy stocks；请使用 rebuild_stocks_lot（stocks_lot 主余额）或对应审计工具。"
        )

    @staticmethod
    async def rebuild_stocks_lot(
        session: AsyncSession,
        *,
        time_from: Optional[str] = None,
        time_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Phase 4E：全量或时间切片重建 stocks_lot（lot-world 主余额）。

        步骤：
        1) TRUNCATE stocks_lot
        2) 从 ledger 按 (warehouse_id, item_id, lot_id_key) 聚合 sum(delta)
           - lot_id_key = COALESCE(lot_id, 0)
           - lot_id_key=0 -> lot_id=NULL（无 lot 槽位）
        3) 只写 qty != 0 的槽位

        注意：
        - 不依赖 lots 主档（但 lot_id_key>0 必须能在 FK 上通过；正常情况 ledger.lot_id 已保证）
        """
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
                CASE WHEN COALESCE(lot_id, 0) = 0 THEN NULL ELSE COALESCE(lot_id, 0) END AS lot_id,
                SUM(delta) AS qty
            FROM stock_ledger
            {where_sql}
            GROUP BY warehouse_id, item_id, COALESCE(lot_id, 0)
            HAVING SUM(delta) != 0;
        """

        await session.execute(text(insert_sql), params)

        summary_sql = """
            SELECT COUNT(*) AS slot_count,
                   COALESCE(SUM(qty), 0) AS total_qty
            FROM stocks_lot
        """
        summary = (await session.execute(text(summary_sql))).mappings().first()
        slot_count = int(summary["slot_count"])
        total_qty = int(summary["total_qty"])

        return {
            "slot_count": slot_count,
            "total_qty": total_qty,
        }
