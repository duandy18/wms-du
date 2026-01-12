# app/api/routers/stock_ledger_routes_export.py
from __future__ import annotations

import csv
from datetime import datetime
from io import BytesIO, StringIO

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.stock_ledger import StockLedger
from app.schemas.stock_ledger import LedgerQuery

from app.api.routers.stock_ledger_helpers import (
    apply_common_filters_rows,
    exec_rows,
    normalize_time_range,
)


def _build_export_csv_with_sub_reason(rows: list[StockLedger]) -> tuple[BytesIO, str]:
    """
    导出台账 CSV（包含 sub_reason）：

    列：
    id, delta, reason, sub_reason, ref, ref_line, occurred_at, created_at, after_qty,
    item_id, warehouse_id, batch_code, trace_id
    """
    sio = StringIO()
    writer = csv.writer(sio)

    writer.writerow(
        [
            "id",
            "delta",
            "reason",
            "sub_reason",
            "ref",
            "ref_line",
            "occurred_at",
            "created_at",
            "after_qty",
            "item_id",
            "warehouse_id",
            "batch_code",
            "trace_id",
        ]
    )

    for r in rows:
        writer.writerow(
            [
                r.id,
                r.delta,
                r.reason,
                r.sub_reason or "",
                r.ref or "",
                r.ref_line,
                r.occurred_at.isoformat() if hasattr(r.occurred_at, "isoformat") else str(r.occurred_at),
                r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else str(r.created_at),
                r.after_qty,
                r.item_id,
                r.warehouse_id,
                r.batch_code,
                r.trace_id or "",
            ]
        )

    out = BytesIO(sio.getvalue().encode("utf-8-sig"))
    filename = f"stock_ledger_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    out.seek(0)
    return out, filename


def register(router: APIRouter) -> None:
    @router.post("/export")
    async def export_ledger(
        payload: LedgerQuery,
        session: AsyncSession = Depends(get_session),
    ):
        """
        导出台账 CSV：

        - 过滤条件与 /stock/ledger/query 一致（基于 LedgerQuery & occurred_at）；
        - 本次增强：支持 sub_reason 过滤，导出列中包含 sub_reason。
        """
        time_from, time_to = normalize_time_range(payload)

        rows_stmt = select(StockLedger)
        rows_stmt = apply_common_filters_rows(rows_stmt, payload, time_from, time_to)

        # ✅ 增强：sub_reason 过滤（不改 helper，直接在这里补充条件）
        if getattr(payload, "sub_reason", None):
            rows_stmt = rows_stmt.where(StockLedger.sub_reason == payload.sub_reason)

        rows = await exec_rows(session, rows_stmt, payload)

        buf, filename = _build_export_csv_with_sub_reason(rows)
        return StreamingResponse(
            buf,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
