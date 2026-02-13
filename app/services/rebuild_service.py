# app/services/rebuild_service.py
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class RebuildService:
    """
    从 ledger 重算库存余额（stocks），用于审计 / 恢复 / 对账。

    不涉及 batches 主档，不涉及 snapshot_v2。
    单纯以 ledger 累加 δ 构建 stocks。

    ✅ scope 世界观：
    - stocks / stock_ledger 都必须按 scope 隔离
    - rebuild 必须把 scope 一起重建，否则会出现 NULL scope 或串账
    """

    @staticmethod
    async def rebuild_stocks(
        session: AsyncSession,
        *,
        time_from: Optional[str] = None,
        time_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        全量或时间切片重建 stocks。

        步骤：
        1) TRUNCATE stocks
        2) 从 ledger 按 (scope, warehouse,item,batch) 聚合 sum(delta)
        3) 只写 qty != 0 的槽位

        输出：
        {
            "slot_count": M,
            "total_qty": Q
        }
        """

        # 1) 清空 stocks
        await session.execute(text("TRUNCATE TABLE stocks RESTART IDENTITY"))

        # 2) 条件构造（仍沿用字符串拼接，但保持原语义）
        conditions = []
        if time_from:
            conditions.append(f"occurred_at >= '{time_from}'")
        if time_to:
            conditions.append(f"occurred_at <= '{time_to}'")

        where_sql = ""
        if conditions:
            where_sql = "WHERE " + " AND ".join(conditions)

        # 3) 聚合 ledger（必须带 scope）
        insert_sql = f"""
            INSERT INTO stocks (scope, warehouse_id, item_id, batch_code, qty)
            SELECT
                scope,
                warehouse_id,
                item_id,
                batch_code,
                SUM(delta) AS qty
            FROM stock_ledger
            {where_sql}
            GROUP BY scope, warehouse_id, item_id, batch_code
            HAVING SUM(delta) != 0;
        """

        await session.execute(text(insert_sql))

        # 4) 汇总
        summary_sql = """
            SELECT COUNT(*) AS slot_count,
                   COALESCE(SUM(qty), 0) AS total_qty
            FROM stocks
        """
        summary = (await session.execute(text(summary_sql))).mappings().first()
        slot_count = int(summary["slot_count"])
        total_qty = int(summary["total_qty"])

        return {
            "slot_count": slot_count,
            "total_qty": total_qty,
        }
