# app/routers/stock_ledger.py
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.stock_ledger import StockLedger
from app.models.stock import Stock
from app.models.batch import Batch

router = APIRouter(tags=["stock_ledger"])

# ---- 时区：响应统一转 Asia/Shanghai (+08:00)，DB 仍写入 UTC ----
_CST = timezone(timedelta(hours=8))


def _to_cst(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(_CST)


# ---- 每请求独立会话，避免 TestClient 事件循环冲突 ----
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


# ---- 模型 ----
class LedgerQuery(BaseModel):
    stock_id: Optional[int] = None
    batch_code: Optional[str] = None
    reason: Optional[str] = None
    ref: Optional[str] = None
    time_from: Optional[datetime | date] = None
    time_to: Optional[datetime | date] = None
    limit: int = Field(100, ge=1, le=500)
    offset: int = Field(0, ge=0)


class LedgerItem(BaseModel):
    id: int
    occurred_at: datetime
    reason: Optional[str] = None
    ref: Optional[str] = None
    ref_line: Optional[int] = None
    delta: int
    after_qty: Optional[int] = None
    stock_id: Optional[int] = None
    item_id: int


class LedgerQueryResp(BaseModel):
    total: int
    items: List[LedgerItem]


# ---- 基础查询（仅选 id；用于 count + 分页）----
def _build_base_stmt(payload: LedgerQuery):
    # 批次筛选在基础查询阶段通过 ledger.stock_id -> stocks -> batches 完成
    stmt = select(StockLedger.id)

    if payload.batch_code:
        stmt = (
            select(StockLedger.id)
            .join(Stock, Stock.id == StockLedger.stock_id)
            .join(
                Batch,
                and_(
                    Batch.item_id == Stock.item_id,
                    Batch.location_id == Stock.location_id,
                ),
            )
            .where(Batch.batch_code == payload.batch_code)
        )

    if payload.stock_id is not None:
        stmt = stmt.where(StockLedger.stock_id == payload.stock_id)
    if payload.reason:
        stmt = stmt.where(StockLedger.reason == payload.reason)
    if payload.ref:
        stmt = stmt.where(StockLedger.ref == payload.ref)

    if payload.time_from is not None:
        t0 = payload.time_from
        if isinstance(t0, date) and not isinstance(t0, datetime):
            t0 = datetime.combine(t0, datetime.min.time(), tzinfo=timezone.utc)
        stmt = stmt.where(StockLedger.occurred_at >= t0)

    if payload.time_to is not None:
        t1 = payload.time_to
        if isinstance(t1, date) and not isinstance(t1, datetime):
            t1 = datetime.combine(t1, datetime.max.time(), tzinfo=timezone.utc)
        stmt = stmt.where(StockLedger.occurred_at <= t1)

    return stmt


# ---- 路由 ----
@router.post("/stock/ledger/query", response_model=LedgerQueryResp)
async def query_ledger(
    payload: LedgerQuery,
    session: AsyncSession = Depends(_get_session),
) -> LedgerQueryResp:
    base_stmt = _build_base_stmt(payload)

    total = (
        await session.execute(select(func.count()).select_from(base_stmt.subquery()))
    ).scalar_one()

    ids_sub = (
        base_stmt.order_by(StockLedger.id.desc())
        .limit(payload.limit)
        .offset(payload.offset)
        .subquery()
    )

    # 详情：直接读取 ledger.item_id（不再为详情 JOIN stocks）
    rows = (
        await session.execute(
            select(
                StockLedger.id,
                StockLedger.occurred_at,
                StockLedger.reason,
                StockLedger.ref,
                StockLedger.ref_line,
                StockLedger.delta,
                StockLedger.after_qty,
                StockLedger.stock_id,
                StockLedger.item_id,
            )
            .where(StockLedger.id.in_(select(ids_sub.c.id)))
            .order_by(StockLedger.id.desc())
        )
    ).all()

    items = [
        LedgerItem(
            id=int(r.id),
            occurred_at=_to_cst(r.occurred_at),  # 输出统一为 CST(+08:00)
            reason=r.reason,
            ref=r.ref,
            ref_line=r.ref_line,
            delta=int(r.delta or 0),
            after_qty=(int(r.after_qty) if r.after_qty is not None else None),
            stock_id=(int(r.stock_id) if r.stock_id is not None else None),
            item_id=int(r.item_id),
        )
        for r in rows
    ]

    return LedgerQueryResp(total=int(total), items=items)
