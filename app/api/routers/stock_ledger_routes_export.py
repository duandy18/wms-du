# app/api/routers/stock_ledger_routes_export.py
from __future__ import annotations

import csv
from datetime import datetime
from io import BytesIO, StringIO

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.lot_code_contract import normalize_optional_lot_code
from app.api.routers.stock_ledger_helpers import (
    apply_common_filters_rows,
    exec_rows,
    normalize_time_range,
)
from app.db.session import get_session
from app.models.lot import Lot
from app.models.stock_ledger import StockLedger
from app.schemas.stock_ledger import LedgerQuery


def _build_export_csv_with_sub_reason(rows: list[StockLedger], lot_code_map: dict[int, str | None]) -> tuple[BytesIO, str]:
    """
    导出台账 CSV（包含 sub_reason）：

    列：
    id, delta, reason, sub_reason, ref, ref_line, occurred_at, created_at, after_qty,
    item_id, warehouse_id, batch_code(展示码), lot_id, trace_id
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
            "lot_code",

            "batch_code",
            "lot_id",
            "trace_id",
        ]
    )

    for r in rows:
        lot_id = getattr(r, "lot_id", None)
        batch_code = lot_code_map.get(int(lot_id)) if lot_id is not None else None

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
                batch_code,
                batch_code,
                lot_id,
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
        - 支持 sub_reason 过滤，导出列中包含 sub_reason。
        """
        # ✅ 查询级 batch_code 归一（None/空串/'None' -> None）
        norm_bc = normalize_optional_lot_code(getattr(payload, "batch_code", None))
        if getattr(payload, "batch_code", None) != norm_bc:
            payload = payload.model_copy(update={"batch_code": norm_bc})

        time_from, time_to = normalize_time_range(payload)

        rows_stmt = select(StockLedger)
        rows_stmt = apply_common_filters_rows(rows_stmt, payload, time_from, time_to)

        # ✅ sub_reason 过滤（保持原行为）
        if getattr(payload, "sub_reason", None):
            rows_stmt = rows_stmt.where(StockLedger.sub_reason == payload.sub_reason)

        rows = await exec_rows(session, rows_stmt, payload)

        # ✅ 批量补齐展示 batch_code：lots.lot_code by lot_id
        lot_ids = sorted({int(getattr(r, "lot_id")) for r in rows if getattr(r, "lot_id", None) is not None})
        lot_code_map: dict[int, str | None] = {}
        if lot_ids:
            res = await session.execute(select(Lot.id, Lot.lot_code).where(Lot.id.in_(lot_ids)))
            for lot_id, lot_code in res.all():
                lot_code_map[int(lot_id)] = lot_code

        buf, filename = _build_export_csv_with_sub_reason(rows, lot_code_map)
        return StreamingResponse(
            buf,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
