# app/api/routers/stock_ledger_routes_summary.py
from __future__ import annotations

from typing import List

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.item import Item
from app.models.stock_ledger import StockLedger
from app.schemas.stock_ledger import LedgerQuery, LedgerReasonStat, LedgerSummary

from app.api.routers.stock_ledger_helpers import build_common_filters, normalize_time_range


def register(router: APIRouter) -> None:
    @router.post("/summary", response_model=LedgerSummary)
    async def summarize_ledger(
        payload: LedgerQuery,
        session: AsyncSession = Depends(get_session),
    ) -> LedgerSummary:
        """
        台账统计接口（供前端直接渲染统计表/图）：

        - 使用与明细查询相同的过滤条件（LedgerQuery）；
        - 按 reason 聚合 count / sum(delta)；
        - 不返回明细 rows，只返回统计结果。
        """
        time_from, time_to = normalize_time_range(payload)
        conditions = build_common_filters(payload, time_from, time_to)

        stmt = select(
            StockLedger.reason,
            func.count(StockLedger.id).label("cnt"),
            func.sum(StockLedger.delta).label("total_delta"),
        ).select_from(StockLedger)

        # 若使用 item_keyword，则需要 JOIN items
        if payload.item_keyword:
            kw = f"%{payload.item_keyword.strip()}%"
            stmt = stmt.join(Item, Item.id == StockLedger.item_id)
            conditions.append(
                sa.or_(
                    Item.name.ilike(kw),
                    Item.sku.ilike(kw),
                )
            )

        if conditions:
            stmt = stmt.where(sa.and_(*conditions))
        stmt = stmt.group_by(StockLedger.reason)

        result = await session.execute(stmt)

        stats: List[LedgerReasonStat] = []
        net_delta = 0

        for row in result.mappings():
            reason = row["reason"]
            cnt = int(row["cnt"] or 0)
            total_delta = int(row["total_delta"] or 0)
            net_delta += total_delta

            stats.append(
                LedgerReasonStat(
                    reason=reason,
                    count=cnt,
                    total_delta=total_delta,
                )
            )

        return LedgerSummary(
            filters=payload,
            by_reason=stats,
            net_delta=net_delta,
        )
