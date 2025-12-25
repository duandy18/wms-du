# app/api/routers/stock_ledger_routes_query.py
from __future__ import annotations


from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.stock_ledger import StockLedger
from app.schemas.stock_ledger import LedgerList, LedgerRow, LedgerQuery

from app.api.routers.stock_ledger_helpers import (
    build_base_ids_stmt,
    infer_movement_type,
    normalize_time_range,
)


def register(router: APIRouter) -> None:
    @router.post("/query", response_model=LedgerList)
    async def query_ledger(
        payload: LedgerQuery,
        session: AsyncSession = Depends(get_session),
    ) -> LedgerList:
        """
        查询库存台账明细（翻流水）：

        - 使用 LedgerQuery 过滤条件；
        - 默认按 occurred_at 降序 + id 降序排序；
        - 不带 item/warehouse/batch 等过滤时，即为“总账视图”（仅按时间窗口截取）。
        """
        time_from, time_to = normalize_time_range(payload)

        # 1) 根据过滤条件构造 id 子查询
        ids_stmt = build_base_ids_stmt(payload, time_from, time_to)
        ids_subq = ids_stmt.subquery()

        # 2) 计算总条数
        total = (await session.execute(select(func.count()).select_from(ids_subq))).scalar_one()

        # 3) 查询当前页明细
        list_stmt = (
            select(StockLedger)
            .where(StockLedger.id.in_(select(ids_subq.c.id)))
            .order_by(StockLedger.occurred_at.desc(), StockLedger.id.desc())
            .limit(payload.limit)
            .offset(payload.offset)
        )

        rows: list[StockLedger] = (await session.execute(list_stmt)).scalars().all()

        return LedgerList(
            total=total,
            items=[
                LedgerRow(
                    id=r.id,
                    delta=r.delta,
                    reason=r.reason,
                    ref=r.ref,
                    ref_line=r.ref_line,
                    occurred_at=r.occurred_at,
                    created_at=r.created_at,
                    after_qty=r.after_qty,
                    item_id=r.item_id,
                    warehouse_id=r.warehouse_id,
                    batch_code=r.batch_code,
                    trace_id=r.trace_id,
                    movement_type=infer_movement_type(r.reason),
                )
                for r in rows
            ],
        )
