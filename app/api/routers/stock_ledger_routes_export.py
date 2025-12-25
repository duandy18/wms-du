# app/api/routers/stock_ledger_routes_export.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.stock_ledger import StockLedger
from app.schemas.stock_ledger import LedgerQuery

from app.api.routers.stock_ledger_helpers import (
    apply_common_filters_rows,
    build_export_csv,
    exec_rows,
    normalize_time_range,
)


def register(router: APIRouter) -> None:
    @router.post("/export")
    async def export_ledger(
        payload: LedgerQuery,
        session: AsyncSession = Depends(get_session),
    ):
        """
        导出台账 CSV：

        - 过滤条件与 /stock/ledger/query 一致（基于 LedgerQuery & occurred_at）；
        - 列：id, delta, reason, ref, occurred_at, created_at, after_qty。
        """
        time_from, time_to = normalize_time_range(payload)

        rows_stmt = select(StockLedger)
        rows_stmt = apply_common_filters_rows(rows_stmt, payload, time_from, time_to)
        rows = await exec_rows(session, rows_stmt, payload)

        buf, filename = build_export_csv(rows)
        return StreamingResponse(
            buf,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
