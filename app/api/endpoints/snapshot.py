from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.snapshot import SnapshotRunResult, StockSnapshotRead, TrendPoint
from app.services.snapshot_service import SnapshotService

router = APIRouter(prefix="/snapshot", tags=["snapshot"])


@router.post("/run", response_model=SnapshotRunResult)
async def run_snapshot(
    d: date = Query(..., alias="date", description="对齐到当天的日期（YYYY-MM-DD）"),
    session: AsyncSession = Depends(get_session),
):
    """
    生成某天的库存快照（幂等 UPSERT）。
    """
    affected = await SnapshotService.run_for_date(session, d)
    return SnapshotRunResult(date=d, affected_rows=affected)


@router.post("/run-range", response_model=SnapshotRunResult)
async def run_snapshot_range(
    frm: date = Query(..., alias="from", description="起始日期（含）"),
    to: date = Query(..., alias="to", description="结束日期（含）"),
    session: AsyncSession = Depends(get_session),
):
    """
    生成一段日期范围内的库存快照，便于回灌历史数据。
    """
    if to < frm:
        raise HTTPException(status_code=400, detail="'to' must be >= 'from'")
    affected = await SnapshotService.run_range(session, frm, to)
    return SnapshotRunResult(date=to, affected_rows=affected)


@router.get("", response_model=list[StockSnapshotRead])
async def list_snapshots(  # noqa: PLR0913
    d: date | None = Query(None, alias="date", description="不填则为所有日期"),
    item_id: int | None = Query(None, description="按商品过滤"),
    warehouse_id: int | None = Query(None, description="按仓库过滤"),
    location_id: int | None = Query(None, description="按库位过滤"),
    batch_id: int | None = Query(None, description="按批次过滤"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """
    快照明细列表（可过滤 + 分页）。
    """
    return await SnapshotService.list_snapshots(
        session=session,
        d=d,
        item_id=item_id,
        warehouse_id=warehouse_id,
        location_id=location_id,
        batch_id=batch_id,
        limit=limit,
        offset=offset,
    )


# === 首页：库存总览（分页 + 搜索） ===
@router.get("/inventory")
async def inventory_snapshot(
    q: str | None = Query(None, description="模糊搜索 items.name / items.sku"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """
    返回分页搜索结果：
    {
      "total": 123, "offset": 0, "limit": 20,
      "rows": [{
        "item_id": 1, "item_name": "...", "sku": "...",
        "total_qty": 100,
        "top2_locations": [{"location_id":3,"qty":70},{"location_id":7,"qty":30}],
        "earliest_expiry": "YYYY-MM-DD" | null,
        "near_expiry": true|false
      }]
    }
    """
    return await SnapshotService.query_inventory_snapshot_paged(
        session=session, q=q, offset=offset, limit=limit
    )


@router.get("/trends", response_model=list[TrendPoint])
async def trends(
    item_id: int = Query(..., description="商品 ID"),
    frm: date = Query(..., description="开始日期（含）"),
    to: date = Query(..., description="结束日期（含）"),
    session: AsyncSession = Depends(get_session),
):
    """
    趋势：按天聚合 on_hand / available。
    """
    if to < frm:
        raise HTTPException(status_code=400, detail="'to' must be >= 'from'")
    return await SnapshotService.trends(session, item_id=item_id, frm=frm, to=to)
