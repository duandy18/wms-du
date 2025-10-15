# app/api/endpoints/snapshot.py
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 你项目里的依赖保持不变（若你的会话依赖名为 get_async_session，请改成它）
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
    由 SnapshotService 负责对齐与计算。
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
    返回值的 affected_rows 表示整个区间的累计写入/更新行数。
    """
    if to < frm:
        raise HTTPException(status_code=400, detail="'to' must be >= 'from'")
    affected = await SnapshotService.run_range(session, frm, to)
    return SnapshotRunResult(date=to, affected_rows=affected)


@router.get("", response_model=list[StockSnapshotRead])
async def list_snapshots(
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
    快照列表（可过滤 + 分页）。
    为避免 ORM 模型到 Pydantic 的隐式转换问题，使用 SQL 文本 + RowMapping。
    """
    sql = """
    SELECT
      id, snapshot_date, warehouse_id, location_id, item_id, batch_id,
      qty_on_hand, qty_allocated, qty_available, expiry_date, age_days, created_at
    FROM stock_snapshots
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

    # 将 RowMapping -> dict，并显式转为 Python 基本类型，避免 JSON 编码器遇到 Decimal/Row 对象
    def _t(x: Any) -> Any:
        # 这里保守地只把可能是 Decimal 的值转成 float；其余保持原样
        return float(x) if hasattr(x, "as_tuple") else x

    return [
        {
            "id": r["id"],
            "snapshot_date": r["snapshot_date"],
            "warehouse_id": r["warehouse_id"],
            "location_id": r["location_id"],
            "item_id": r["item_id"],
            "batch_id": r["batch_id"],
            "qty_on_hand": int(r["qty_on_hand"]),
            "qty_allocated": int(r["qty_allocated"]),
            "qty_available": int(r["qty_available"]),
            "expiry_date": r["expiry_date"],
            "age_days": r["age_days"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@router.get("/trends", response_model=list[TrendPoint])
async def trends(
    item_id: int = Query(..., description="商品 ID"),
    frm: date = Query(..., description="开始日期（含）"),
    to: date = Query(..., description="结束日期（含）"),
    session: AsyncSession = Depends(get_session),
):
    """
    趋势：按天聚合 on_hand / available。
    依赖模型上的组合索引 ix_ss_item_date(item_id, snapshot_date)。
    """
    if to < frm:
        raise HTTPException(status_code=400, detail="'to' must be >= 'from'")

    sql = """
    SELECT snapshot_date,
           SUM(qty_on_hand)    AS qty_on_hand,
           SUM(qty_available)  AS qty_available
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
    return [
        {
            "snapshot_date": r["snapshot_date"],
            "qty_on_hand": int(r["qty_on_hand"]),
            "qty_available": int(r["qty_available"]),
        }
        for r in rows
    ]


@router.get("/ageing")
async def ageing(
    d: date = Query(..., description="快照日期"),
    item_id: int | None = Query(None),
    warehouse_id: int | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """
    库龄分布：把 qty_on_hand 按 age_days 分桶。
    """
    sql = """
    SELECT
      SUM(CASE WHEN age_days BETWEEN 0 AND 30  THEN qty_on_hand ELSE 0 END) AS d0_30,
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
    # 直接返回映射对象即可（FastAPI 会做 JSON 化）
    return {
        "d0_30": int(row["d0_30"] or 0),
        "d31_60": int(row["d31_60"] or 0),
        "d61_90": int(row["d61_90"] or 0),
        "d90p": int(row["d90p"] or 0),
    }
