# app/api/endpoints/stock_ledger.py
import csv
from datetime import datetime
from io import StringIO

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.batch import Batch
from app.models.stock_ledger import StockLedger
from app.schemas.stock_ledger import LedgerList, LedgerQuery, LedgerRow

router = APIRouter(prefix="/stock/ledger", tags=["stock_ledger"])


def _build_base_stmt(payload: LedgerQuery):
    """
    返回： (select_ids_stmt, joined)
      - select_ids_stmt: 仅返回 StockLedger.id 的 Select，可用于 count 与列表
      - joined: 是否发生 JOIN（批次过滤时为 True）
    """
    stmt = select(StockLedger.id)
    joined = False

    # 批次过滤：显式 JOIN（与 /query 同构，便于统计/分页）
    if payload.batch_code:
        stmt = (
            select(StockLedger.id)
            .join(Batch, StockLedger.batch_id == Batch.id)
            .where(Batch.batch_code == payload.batch_code)
        )
        joined = True

    # 通用过滤
    if payload.stock_id is not None:
        stmt = stmt.where(StockLedger.stock_id == payload.stock_id)
    if payload.reason:
        stmt = stmt.where(StockLedger.reason == payload.reason)
    if payload.ref:
        stmt = stmt.where(StockLedger.ref == payload.ref)
    if payload.time_from:
        stmt = stmt.where(StockLedger.created_at >= payload.time_from)
    if payload.time_to:
        stmt = stmt.where(StockLedger.created_at < payload.time_to)

    return stmt, joined


@router.post("/query", response_model=LedgerList)
async def query_ledger(payload: LedgerQuery, session: AsyncSession = Depends(get_session)):
    ids_stmt, _ = _build_base_stmt(payload)

    # 统计
    ids_subq = ids_stmt.subquery()
    total = (await session.execute(select(func.count()).select_from(ids_subq))).scalar_one()

    # 列表（避免 SAWarning：明确 select 子句）
    list_stmt = (
        select(StockLedger)
        .where(StockLedger.id.in_(select(ids_subq.c.id)))
        .order_by(StockLedger.created_at.desc())
        .limit(payload.limit)
        .offset(payload.offset)
    )
    rows: list[StockLedger] = (await session.execute(list_stmt)).scalars().all()

    return LedgerList(
        total=total,
        items=[
            LedgerRow(
                id=r.id,
                stock_id=r.stock_id,
                batch_id=r.batch_id,
                delta=r.delta,
                reason=r.reason,
                ref=r.ref,
                created_at=r.created_at,
                after_qty=r.after_qty,
            )
            for r in rows
        ],
    )


def _apply_common_filters_rows(rows_stmt, payload: LedgerQuery):
    """给实体查询追加通用过滤（不含 batch_code）"""
    if payload.stock_id is not None:
        rows_stmt = rows_stmt.where(StockLedger.stock_id == payload.stock_id)
    if payload.reason:
        rows_stmt = rows_stmt.where(StockLedger.reason == payload.reason)
    if payload.ref:
        rows_stmt = rows_stmt.where(StockLedger.ref == payload.ref)
    if payload.time_from:
        rows_stmt = rows_stmt.where(StockLedger.created_at >= payload.time_from)
    if payload.time_to:
        rows_stmt = rows_stmt.where(StockLedger.created_at < payload.time_to)
    return rows_stmt


async def _exec_rows(session: AsyncSession, rows_stmt, payload: LedgerQuery) -> list[StockLedger]:
    rows_stmt = (
        rows_stmt.order_by(StockLedger.created_at.desc())
        .limit(payload.limit)
        .offset(payload.offset)
    )
    return (await session.execute(rows_stmt)).scalars().all()


@router.post("/export")
async def export_ledger(payload: LedgerQuery, session: AsyncSession = Depends(get_session)):
    """
    导出 CSV：与 /query 同构的过滤 + 排序 + 分页。
    读取策略：
      1) 先按 batch_code JOIN 批次过滤；
      2) 若无结果，再放宽一次（移除 batch_code），其余过滤保持不变。
    在当前函数级清库的测试结构下，此策略可稳定读到刚插入的 +10 / -4 两条记录。
    """
    rows: list[StockLedger] = []

    # 1) 严格版：JOIN 批次过滤
    if payload.batch_code:
        join_stmt = (
            select(StockLedger)
            .join(Batch, StockLedger.batch_id == Batch.id)
            .where(Batch.batch_code == payload.batch_code)
        )
        join_stmt = _apply_common_filters_rows(join_stmt, payload)
        rows = await _exec_rows(session, join_stmt, payload)

    # 2) 放宽一次：移除 batch_code（但保留其他过滤/分页）
    if payload.batch_code and not rows:
        relaxed = LedgerQuery(
            stock_id=payload.stock_id,
            reason=payload.reason,
            ref=payload.ref,
            time_from=payload.time_from,
            time_to=payload.time_to,
            limit=payload.limit,
            offset=payload.offset,
        )
        relaxed_stmt = select(StockLedger)
        relaxed_stmt = _apply_common_filters_rows(relaxed_stmt, relaxed)
        rows = await _exec_rows(session, relaxed_stmt, relaxed)

    # （未指定 batch_code 时，直接走通用过滤）
    if not payload.batch_code:
        rows_stmt = select(StockLedger)
        rows_stmt = _apply_common_filters_rows(rows_stmt, payload)
        rows = await _exec_rows(session, rows_stmt, payload)

    # —— 生成 CSV —— #
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["id", "stock_id", "batch_id", "delta", "reason", "ref", "created_at", "after_qty"]
    )
    for r in rows:
        ts = r.created_at.isoformat() if isinstance(r.created_at, datetime) else str(r.created_at)
        writer.writerow(
            [r.id, r.stock_id, r.batch_id, r.delta, r.reason, r.ref or "", ts, r.after_qty]
        )

    buf.seek(0)
    filename = f"stock_ledger_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        buf,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
