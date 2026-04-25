# app/wms/analysis/services/rebuild_stocks_service.py
from __future__ import annotations

import os
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
        allow_truncate: bool = False,
        allow_in_prod: bool = False,
    ) -> Dict[str, Any]:
        """
        ⚠️ 危险运维工具：从 stock_ledger 重建 stocks_lot（balance 表）。

        设计定位：
        - 用于 dev/test 环境的修复 / 回放 / 灾备演练
        - 不属于业务执行路径（业务写入必须走 lot-only 库存写入原语）

        安全护栏：
        - 默认拒绝执行，必须显式 allow_truncate=True
        - 默认仅允许 dev/test 环境；生产需再显式 allow_in_prod=True

        参数说明：
        - time_from/time_to：仅用 ledger 的时间窗重建（字符串由调用者保证格式）
        - allow_truncate：是否允许 TRUNCATE stocks_lot（必须为 True 才执行）
        - allow_in_prod：生产环境是否允许（双开关，默认 False）
        """
        if not allow_truncate:
            raise ValueError("rebuild_stocks_lot is dangerous; set allow_truncate=True to proceed.")

        env = (os.getenv("WMS_ENV") or "").strip().lower()
        is_prod_like = env in {"prod", "production"}
        if is_prod_like and not allow_in_prod:
            raise ValueError("rebuild_stocks_lot is blocked in production; set allow_in_prod=True to proceed.")

        # 1) 清空 balance 表（核弹按钮）
        await session.execute(text("TRUNCATE TABLE stocks_lot RESTART IDENTITY"))

        # 2) 选取 ledger 时间窗（可选）
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

        # 3) 从 ledger 聚合重建 balance
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

        # 4) 输出摘要
        summary_sql = """
            SELECT COUNT(*) AS slot_count,
                   COALESCE(SUM(qty), 0) AS total_qty
            FROM stocks_lot
        """
        summary = (await session.execute(text(summary_sql))).mappings().first()

        return {
            "slot_count": int(summary["slot_count"]),
            "total_qty": int(summary["total_qty"]),
            "env": env or None,
            "time_from": time_from,
            "time_to": time_to,
            "allow_truncate": True,
            "allow_in_prod": bool(allow_in_prod),
        }
