# app/wms/ledger/routers/stock_ledger_routes_summary.py
from __future__ import annotations

from typing import List

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.item_test_set import ItemTestSet
from app.models.item_test_set_item import ItemTestSetItem
from app.wms.ledger.models.stock_ledger import StockLedger
from app.wms.ledger.contracts.stock_ledger import LedgerQuery, LedgerReasonStat, LedgerSummary
from app.wms.ledger.helpers.stock_ledger import (
    ITEMS_TABLE,
    build_common_filters,
    normalize_time_range,
)
from app.wms.shared.services.lot_code_contract import normalize_optional_lot_code


def register(router: APIRouter) -> None:
    @router.post("/summary", response_model=LedgerSummary)
    async def summarize_ledger(
        payload: LedgerQuery,
        session: AsyncSession = Depends(get_session),
    ) -> LedgerSummary:
        norm_bc = normalize_optional_lot_code(getattr(payload, "batch_code", None))
        if getattr(payload, "batch_code", None) != norm_bc:
            payload = payload.model_copy(update={"batch_code": norm_bc})

        time_from, time_to = normalize_time_range(payload)
        conditions = build_common_filters(payload, time_from, time_to)

        default_set_id_sq = (
            select(ItemTestSet.id)
            .where(ItemTestSet.code == "DEFAULT")
            .limit(1)
            .scalar_subquery()
        )

        stmt = (
            select(
                StockLedger.reason,
                func.count(StockLedger.id).label("cnt"),
                func.coalesce(func.sum(StockLedger.delta), 0).label("total_delta"),
            )
            .select_from(StockLedger)
            .outerjoin(
                ItemTestSetItem,
                and_(
                    ItemTestSetItem.item_id == StockLedger.item_id,
                    ItemTestSetItem.set_id == default_set_id_sq,
                ),
            )
            .where(ItemTestSetItem.id.is_(None))
        )

        if payload.item_keyword:
            kw = f"%{payload.item_keyword.strip()}%"
            stmt = stmt.join(ITEMS_TABLE, ITEMS_TABLE.c.id == StockLedger.item_id)
            conditions.append(
                sa.or_(
                    ITEMS_TABLE.c.name.ilike(kw),
                    ITEMS_TABLE.c.sku.ilike(kw),
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
