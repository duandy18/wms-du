# app/api/routers/stock_ledger_routes_reconcile.py
from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.batch_code_contract import normalize_optional_batch_code
from app.api.routers.stock_ledger_helpers import normalize_time_range
from app.db.session import get_session
from app.models.stock import Stock
from app.models.stock_ledger import StockLedger
from app.schemas.stock_ledger import LedgerQuery, LedgerReconcileResult, LedgerReconcileRow

_NULL_BATCH_KEY = "__NULL_BATCH__"


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

        找出 (warehouse_id, item_id, batch_code_key) 维度上“不平”的记录：
        - ledger_sum_delta != stock_qty

        过滤条件：
        - 复用 LedgerQuery 中的 warehouse_id / item_id / batch_code（查询级归一后映射到 batch_code_key）；
        - 其它过滤（reason/ref/trace_id）对对账没有意义，此处忽略。
        """
        time_from, time_to = normalize_time_range(payload)

        # ✅ 主线 B：对账维度统一切 batch_code_key（消灭 NULL 吞数据）
        # - 不传 batch_code：不加过滤
        # - 传 "" / "None"：归一为 None -> batch_code_key='__NULL_BATCH__'
        # - 传 "Bxxx"：batch_code_key='Bxxx'
        fields_set = getattr(payload, "model_fields_set", set())
        batch_key_filter: str | None = None
        if "batch_code" in fields_set:
            norm_bc = normalize_optional_batch_code(getattr(payload, "batch_code", None))
            batch_key_filter = _NULL_BATCH_KEY if norm_bc is None else norm_bc

        # 只用库存三元组 + 时间过滤做对账
        conditions = [
            StockLedger.occurred_at >= time_from,
            StockLedger.occurred_at <= time_to,
        ]
        if payload.warehouse_id is not None:
            conditions.append(StockLedger.warehouse_id == payload.warehouse_id)
        if payload.item_id is not None:
            conditions.append(StockLedger.item_id == payload.item_id)
        if batch_key_filter is not None:
            conditions.append(StockLedger.batch_code_key == batch_key_filter)

        stmt = (
            select(
                StockLedger.warehouse_id,
                StockLedger.item_id,
                StockLedger.batch_code,      # 便于人读
                StockLedger.batch_code_key,  # 事实维度
                func.sum(StockLedger.delta).label("ledger_sum_delta"),
                Stock.qty.label("stock_qty"),
            )
            .select_from(StockLedger)
            .join(
                Stock,
                sa.and_(
                    Stock.warehouse_id == StockLedger.warehouse_id,
                    Stock.item_id == StockLedger.item_id,
                    Stock.batch_code_key == StockLedger.batch_code_key,
                ),
            )
            .where(sa.and_(*conditions))
            .group_by(
                StockLedger.warehouse_id,
                StockLedger.item_id,
                StockLedger.batch_code,
                StockLedger.batch_code_key,
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
