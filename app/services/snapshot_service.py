# app/services/snapshot_service.py
from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SnapshotService:
    """
    v1.0 · 薄编排快照服务
    - 生成：调用数据库过程 snapshot_today()（幂等 UPSERT，粒度 item+location）
    - 读取：只读视图 v_three_books / v_snapshot_totals
    - 不在 Python 里重算快照，确保与数据库侧口径一致
    """

    @staticmethod
    async def run(session: AsyncSession) -> Dict[str, Any]:
        # 幂等：过程内部 ON CONFLICT 更新，允许多次调用
        await session.execute(text("CALL snapshot_today()"))
        # 读取三账对照视图
        row = await session.execute(text("SELECT * FROM v_three_books"))
        m = row.mappings().first() or {}
        return dict(m)

    @staticmethod
    async def totals(session: AsyncSession, *, day: Optional[date] = None) -> Dict[str, Any]:
        if day is None:
            q = text(
                """
                SELECT snapshot_date, sum_on_hand, sum_available, sum_allocated
                FROM v_snapshot_totals
                WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM v_snapshot_totals)
                """
            )
            row = await session.execute(q)
        else:
            q = text(
                """
                SELECT snapshot_date, sum_on_hand, sum_available, sum_allocated
                FROM v_snapshot_totals
                WHERE snapshot_date=:d
                """
            )
            row = await session.execute(q, {"d": day})
        return dict(row.mappings().first() or {})

    # 兼容旧签名：如果外部仍调用 run_for_date，则直接复用 run()
    @staticmethod
    async def run_for_date(
        session: AsyncSession, day: date, *, sync_unbatched_from_stocks: bool = False
    ) -> Dict[str, Any]:
        return await SnapshotService.run(session)
