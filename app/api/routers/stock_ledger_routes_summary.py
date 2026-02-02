# app/api/routers/stock_ledger_routes_summary.py
from __future__ import annotations

from typing import List

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.batch_code_contract import normalize_optional_batch_code
from app.api.routers.stock_ledger_helpers import build_common_filters, normalize_time_range
from app.db.session import get_session
from app.models.item import Item
from app.models.stock_ledger import StockLedger
from app.schemas.stock_ledger import LedgerQuery, LedgerReasonStat, LedgerSummary


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
        # ✅ 主线 B：查询级 batch_code 归一（None/空串/'None' -> None）
        # helper 内会基于 batch_code_key 做过滤；这里先做入口层防回潮。
        norm_bc = normalize_optional_batch_code(getattr(payload, "batch_code", None))
        if getattr(payload, "batch_code", None) != norm_bc:
            payload = payload.model_copy(update={"batch_code": norm_bc})

        time_from, time_to = normalize_time_range(payload)
        conditions = build_common_filters(payload, time_from, time_to)

        stmt = (
            select(
                StockLedger.reason,
                func.count(StockLedger.id).label("cnt"),
                func.sum(StockLedger.delta).label("total_delta"),
            )
            .select_from(StockLedger)
        )

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
