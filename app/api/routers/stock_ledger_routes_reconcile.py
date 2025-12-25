# app/api/routers/stock_ledger_routes_reconcile.py
from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.stock import Stock
from app.models.stock_ledger import StockLedger
from app.schemas.stock_ledger import LedgerQuery, LedgerReconcileResult, LedgerReconcileRow

from app.api.routers.stock_ledger_helpers import normalize_time_range


def register(router: APIRouter) -> None:
    @router.post("/reconcile", response_model=LedgerReconcileResult)
    async def reconcile_ledger(
        payload: LedgerQuery,
        session: AsyncSession = Depends(get_session),
    ) -> LedgerReconcileResult:
        """
        台账对账接口：

        在指定时间窗口内（基于 occurred_at），对比：

          SUM(delta)  vs  stocks.qty

        找出 (warehouse_id, item_id, batch_code) 维度上“不平”的记录：
        - ledger_sum_delta != stock_qty

        过滤条件：
        - 复用 LedgerQuery 中的 warehouse_id / item_id / batch_code；
        - 其它过滤（reason/ref/trace_id）对对账没有意义，此处忽略。
        """
        time_from, time_to = normalize_time_range(payload)

        # 只用库存三元组 + 时间过滤做对账
        conditions = [
            StockLedger.occurred_at >= time_from,
            StockLedger.occurred_at <= time_to,
        ]
        if payload.warehouse_id is not None:
            conditions.append(StockLedger.warehouse_id == payload.warehouse_id)
        if payload.item_id is not None:
            conditions.append(StockLedger.item_id == payload.item_id)
        if payload.batch_code:
            conditions.append(StockLedger.batch_code == payload.batch_code)

        stmt = (
            select(
                StockLedger.warehouse_id,
                StockLedger.item_id,
                StockLedger.batch_code,
                func.sum(StockLedger.delta).label("ledger_sum_delta"),
                Stock.qty.label("stock_qty"),
            )
            .select_from(StockLedger)
            .join(
                Stock,
                sa.and_(
                    Stock.warehouse_id == StockLedger.warehouse_id,
                    Stock.item_id == StockLedger.item_id,
                    Stock.batch_code == StockLedger.batch_code,
                ),
            )
            .where(sa.and_(*conditions))
            .group_by(
                StockLedger.warehouse_id,
                StockLedger.item_id,
                StockLedger.batch_code,
                Stock.qty,
            )
            .having(func.sum(StockLedger.delta) != Stock.qty)
        )

        result = await session.execute(stmt)

        rows: list[LedgerReconcileRow] = []
        for row in result.mappings():
            wh_id = row["warehouse_id"]
            item_id = row["item_id"]
            batch_code = row["batch_code"]
            ledger_sum = int(row["ledger_sum_delta"] or 0)
            stock_qty = int(row["stock_qty"] or 0)
            diff = ledger_sum - stock_qty

            rows.append(
                LedgerReconcileRow(
                    warehouse_id=wh_id,
                    item_id=item_id,
                    batch_code=batch_code,
                    ledger_sum_delta=ledger_sum,
                    stock_qty=stock_qty,
                    diff=diff,
                )
            )

        return LedgerReconcileResult(rows=rows)
