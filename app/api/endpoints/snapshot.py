from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session  # 你现有的依赖
from app.schemas.snapshot import SnapshotRunResult, StockSnapshotRead, TrendPoint
from app.services.snapshot_service import SnapshotService

router = APIRouter(prefix="/snapshot", tags=["snapshot"])


@router.post("/run", response_model=SnapshotRunResult)
async def run_snapshot(
    d: date = Query(..., alias="date"),
    session: AsyncSession = Depends(get_session),
):
    affected = await SnapshotService.run_for_date(session, d)
    return SnapshotRunResult(date=d, affected_rows=affected)


@router.post("/run-range", response_model=SnapshotRunResult)
async def run_snapshot_range(
    frm: date = Query(..., alias="from"),
    to: date = Query(..., alias="to"),
    session: AsyncSession = Depends(get_session),
):
    if to < frm:
        raise HTTPException(status_code=400, detail="'to' must be >= 'from'")
    affected = await SnapshotService.run_range(session, frm, to)
    # 语义上返回 to 日的汇总，affected_rows 表示整个区间的行数（方便日志）
    return SnapshotRunResult(date=to, affected_rows=affected)


@router.get("", response_model=list[StockSnapshotRead])
async def list_snapshots(
    d: date | None = Query(None, alias="date"),
    item_id: int | None = None,
    warehouse_id: int | None = None,
    location_id: int | None = None,
    batch_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    limit: int = 100,
    offset: int = 0,
):
    sql = """
    SELECT * FROM stock_snapshots
    WHERE (:d IS NULL OR snapshot_date = :d)
      AND (:item_id IS NULL OR item_id = :item_id)
      AND (:warehouse_id IS NULL OR warehouse_id = :warehouse_id)
      AND (:location_id IS NULL OR location_id = :location_id)
      AND (:batch_id IS NULL OR batch_id = :batch_id)
    ORDER BY snapshot_date DESC, item_id
    LIMIT :limit OFFSET :offset
    """
    rows = (
        (
            await session.execute(
                text(sql),
                {
                    "d": d,
                    "item_id": item_id,
                    "warehouse_id": warehouse_id,
                    "location_id": location_id,
                    "batch_id": batch_id,
                    "limit": limit,
                    "offset": offset,
                },
            )
        )
        .mappings()
        .all()
    )
    return rows


@router.get("/trends", response_model=list[TrendPoint])
async def trends(
    item_id: int,
    frm: date,
    to: date,
    session: AsyncSession = Depends(get_session),
):
    sql = """
    SELECT snapshot_date,
           SUM(qty_on_hand) AS qty_on_hand,
           SUM(qty_available) AS qty_available
    FROM stock_snapshots
    WHERE item_id = :item_id
      AND snapshot_date BETWEEN :frm AND :to
    GROUP BY snapshot_date
    ORDER BY snapshot_date
    """
    rows = (
        (await session.execute(text(sql), {"item_id": item_id, "frm": frm, "to": to}))
        .mappings()
        .all()
    )
    return rows


@router.get("/ageing")
async def ageing(
    d: date,
    item_id: int | None = None,
    warehouse_id: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    sql = """
    SELECT
      SUM(CASE WHEN age_days BETWEEN 0 AND 30 THEN qty_on_hand ELSE 0 END) AS d0_30,
      SUM(CASE WHEN age_days BETWEEN 31 AND 60 THEN qty_on_hand ELSE 0 END) AS d31_60,
      SUM(CASE WHEN age_days BETWEEN 61 AND 90 THEN qty_on_hand ELSE 0 END) AS d61_90,
      SUM(CASE WHEN age_days > 90 THEN qty_on_hand ELSE 0 END)             AS d90p
    FROM stock_snapshots
    WHERE snapshot_date = :d
      AND (:item_id IS NULL OR item_id = :item_id)
      AND (:warehouse_id IS NULL OR warehouse_id = :warehouse_id)
    """
    row = (
        (
            await session.execute(
                text(sql), {"d": d, "item_id": item_id, "warehouse_id": warehouse_id}
            )
        )
        .mappings()
        .one()
    )
    return row
