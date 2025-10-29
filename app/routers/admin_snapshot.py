from __future__ import annotations

import os
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

router = APIRouter(tags=["snapshot"])

try:
    from app.models.stock_snapshot import StockSnapshot
except Exception:  # pragma: no cover
    from app.models.stock_snapshots import StockSnapshot

# 每请求独立引擎/会话，避免跨事件循环
async def _get_session(_req: Request):
    db_url = os.environ.get("DATABASE_URL", "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms")
    async_url = db_url.replace("+psycopg", "+asyncpg") if "+psycopg" in db_url else db_url
    engine = create_async_engine(async_url, future=True, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with maker() as session:
            yield session
    finally:
        await engine.dispose()

class TrendItem(BaseModel):
    snapshot_date: date
    qty_on_hand: int
    qty_available: Optional[int] = None

@router.get("/snapshot/trends", response_model=List[TrendItem])
async def get_snapshot_trends(
    item_id: int,
    frm: date,
    to: date,
    session: AsyncSession = Depends(_get_session),
) -> List[TrendItem]:
    if frm > to:
        frm, to = to, frm

    has_qty_available = hasattr(StockSnapshot, "qty_available")
    cols = [StockSnapshot.snapshot_date, func.coalesce(StockSnapshot.qty_on_hand, 0).label("qty_on_hand")]
    if has_qty_available:
        cols.append(StockSnapshot.qty_available)

    stmt = (
        select(*cols)
        .where(
            StockSnapshot.item_id == item_id,
            StockSnapshot.snapshot_date >= frm,
            StockSnapshot.snapshot_date <= to,
        )
        .order_by(StockSnapshot.snapshot_date.asc())
    )
    rows = (await session.execute(stmt)).all()

    items: List[TrendItem] = []
    for r in rows:
        snap_day = getattr(r, "snapshot_date", None) or r[0]
        qoh = getattr(r, "qty_on_hand", None) or r[1]
        qa = None
        if has_qty_available:
            qa = getattr(r, "qty_available", None)
            if qa is None and len(r) > 2:
                qa = r[2]
        items.append(
            TrendItem(
                snapshot_date=snap_day,
                qty_on_hand=int(qoh or 0),
                qty_available=(int(qa) if qa is not None else None),
            )
        )
    return items
