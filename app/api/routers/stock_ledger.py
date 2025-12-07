from __future__ import annotations

import csv
import logging
from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import List, Tuple

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.item import Item
from app.models.stock import Stock
from app.models.stock_ledger import StockLedger
from app.schemas.stock_ledger import (
    LedgerList,
    LedgerQuery,
    LedgerReasonStat,
    LedgerReconcileResult,
    LedgerReconcileRow,
    LedgerRow,
    LedgerSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stock/ledger", tags=["stock_ledger"])


# ========= 内部工具函数 =========
def _normalize_time_range(q: LedgerQuery) -> Tuple[datetime, datetime]:
    """
    规范化 time_from / time_to：

    - 两者都为空：默认最近 7 天；
    - 只填了一个：自动补另一个；
    - 限制最大跨度 90 天，避免误查全库。
    """
    now = datetime.now(timezone.utc)

    time_to = q.time_to or now
    time_from = q.time_from or (time_to - timedelta(days=7))

    if time_to < time_from:
        raise HTTPException(status_code=400, detail="'time_to' must be >= 'time_from'")

    max_span = timedelta(days=90)
    if time_to - time_from > max_span:
        raise HTTPException(
            status_code=400,
            detail="时间范围过大，请缩小到 90 天以内（<= 90 天）。",
        )

    return time_from, time_to


def _build_common_filters(q: LedgerQuery, time_from: datetime, time_to: datetime):
    """
    根据查询模型构建 SQLAlchemy 过滤条件列表（不包含 item_keyword 模糊搜索）。
    """
    conditions = [
        StockLedger.occurred_at >= time_from,
        StockLedger.occurred_at <= time_to,
    ]

    if q.item_id is not None:
        conditions.append(StockLedger.item_id == q.item_id)

    if q.warehouse_id is not None:
        conditions.append(StockLedger.warehouse_id == q.warehouse_id)

    if q.batch_code:
        conditions.append(StockLedger.batch_code == q.batch_code)

    if q.reason:
        conditions.append(StockLedger.reason == q.reason)

    if q.ref:
        conditions.append(StockLedger.ref == q.ref)

    if q.trace_id:
        conditions.append(StockLedger.trace_id == q.trace_id)

    return conditions


# 新增：根据 reason 推断 movement_type，用于前端显示 / 统计
def _infer_movement_type(reason: str | None) -> str | None:
    if not reason:
        return None
    r = reason.upper()

    # 入库类
    if r in {"RECEIPT", "INBOUND", "INBOUND_RECEIPT"}:
        return "INBOUND"

    # 出库 / 发货类
    if r in {"SHIP", "SHIPMENT", "OUTBOUND_SHIP", "OUTBOUND_COMMIT"}:
        return "OUTBOUND"

    # 盘点类
    if r in {"COUNT", "STOCK_COUNT", "INVENTORY_COUNT"}:
        return "COUNT"

    # 调整类
    if r in {"ADJUSTMENT", "ADJUST", "MANUAL_ADJUST"}:
        return "ADJUST"

    # 退货 / 逆向
    if r in {"RETURN", "RMA", "INBOUND_RETURN"}:
        return "RETURN"

    # 其余暂标记为 UNKNOWN，方便后续从真实数据中细化
    return "UNKNOWN"


def _build_base_ids_stmt(q: LedgerQuery, time_from: datetime, time_to: datetime):
    """
    按查询条件构造基础 SQL（只选中符合条件的 id 列表）：
    - 支持按 item_id / warehouse_id / batch_code / reason / ref / trace_id / 时间过滤；
    - 支持按 item_keyword 模糊匹配 items.name / items.sku；
    - 不再依赖 stock_id / batch_id，完全对齐当前 StockLedger 模型。
    """
    stmt = select(StockLedger.id).select_from(StockLedger)
    conditions = _build_common_filters(q, time_from, time_to)

    # item_keyword 模糊搜索：name/sku
    if q.item_keyword:
        kw = f"%{q.item_keyword.strip()}%"
        stmt = stmt.join(Item, Item.id == StockLedger.item_id)
        conditions.append(
            sa.or_(
                Item.name.ilike(kw),
                Item.sku.ilike(kw),
            )
        )

    if conditions:
        stmt = stmt.where(sa.and_(*conditions))
    return stmt


# ========= 明细查询（翻流水 / 总账视图） =========
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
    time_from, time_to = _normalize_time_range(payload)

    # 1) 根据过滤条件构造 id 子查询
    ids_stmt = _build_base_ids_stmt(payload, time_from, time_to)
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
                movement_type=_infer_movement_type(r.reason),
            )
            for r in rows
        ],
    )


# ========= 台账统计（给统计图/表用） =========
@router.post("/summary", response_model=LedgerSummary)
async def summarize_ledger(
    payload: LedgerQuery,
    session: AsyncSession = Depends(get_session),
) -> LedgerSummary:
    """
    台账统计接口（供前端直接渲染统计表/图）：

    - 使用与明细查询相同的过滤条件（LedgerQuery）；
    - 按 reason 聚合 count / sum(delta)；
    - 不返回明细 rows，只返回统计结果。
    """
    time_from, time_to = _normalize_time_range(payload)
    conditions = _build_common_filters(payload, time_from, time_to)

    stmt = select(
        StockLedger.reason,
        func.count(StockLedger.id).label("cnt"),
        func.sum(StockLedger.delta).label("total_delta"),
    ).select_from(StockLedger)

    # 若使用 item_keyword，则需要 JOIN items
    if payload.item_keyword:
        kw = f"%{payload.item_keyword.strip()}%"
        stmt = stmt.join(Item, Item.id == StockLedger.item_id)
        conditions.append(
            sa.or_(
                Item.name.ilike(kw),
                Item.sku.ilike(kw),
            )
        )

    if conditions:
        stmt = stmt.where(sa.and_(*conditions))
    stmt = stmt.group_by(StockLedger.reason)

    result = await session.execute(stmt)

    stats: List[LedgerReasonStat] = []
    net_delta = 0

    for row in result.mappings():
        reason = row["reason"]
        cnt = int(row["cnt"] or 0)
        total_delta = int(row["total_delta"] or 0)
        net_delta += total_delta

        stats.append(
            LedgerReasonStat(
                reason=reason,
                count=cnt,
                total_delta=total_delta,
            )
        )

    return LedgerSummary(
        filters=payload,
        by_reason=stats,
        net_delta=net_delta,
    )


# ========= 对账：ledger SUM(delta) vs stocks.qty =========
@router.post("/reconcile", response_model=LedgerReconcileResult)
async def reconcile_ledger(
    payload: LedgerQuery,
    session: AsyncSession = Depends(get_session),
) -> LedgerReconcileResult:
    """
    台账对账接口：

    在指定时间窗口内（基于 occurred_at），对比：

      SUM(delta)  vs  stocks.qty

    找出 (warehouse_id, item_id, batch_code) 维度上“不平”的记录：
    - ledger_sum_delta != stock_qty

    过滤条件：
    - 复用 LedgerQuery 中的 warehouse_id / item_id / batch_code；
    - 其它过滤（reason/ref/trace_id）对对账没有意义，此处忽略。
    """
    time_from, time_to = _normalize_time_range(payload)

    # 只用库存三元组 + 时间过滤做对账
    conditions = [
        StockLedger.occurred_at >= time_from,
        StockLedger.occurred_at <= time_to,
    ]
    if payload.warehouse_id is not None:
        conditions.append(StockLedger.warehouse_id == payload.warehouse_id)
    if payload.item_id is not None:
        conditions.append(StockLedger.item_id == payload.item_id)
    if payload.batch_code:
        conditions.append(StockLedger.batch_code == payload.batch_code)

    stmt = (
        select(
            StockLedger.warehouse_id,
            StockLedger.item_id,
            StockLedger.batch_code,
            func.sum(StockLedger.delta).label("ledger_sum_delta"),
            Stock.qty.label("stock_qty"),
        )
        .select_from(StockLedger)
        .join(
            Stock,
            sa.and_(
                Stock.warehouse_id == StockLedger.warehouse_id,
                Stock.item_id == StockLedger.item_id,
                Stock.batch_code == StockLedger.batch_code,
            ),
        )
        .where(sa.and_(*conditions))
        .group_by(
            StockLedger.warehouse_id,
            StockLedger.item_id,
            StockLedger.batch_code,
            Stock.qty,
        )
        .having(func.sum(StockLedger.delta) != Stock.qty)
    )

    result = await session.execute(stmt)

    rows: list[LedgerReconcileRow] = []
    for row in result.mappings():
        wh_id = row["warehouse_id"]
        item_id = row["item_id"]
        batch_code = row["batch_code"]
        ledger_sum = int(row["ledger_sum_delta"] or 0)
        stock_qty = int(row["stock_qty"] or 0)
        diff = ledger_sum - stock_qty

        rows.append(
            LedgerReconcileRow(
                warehouse_id=wh_id,
                item_id=item_id,
                batch_code=batch_code,
                ledger_sum_delta=ledger_sum,
                stock_qty=stock_qty,
                diff=diff,
            )
        )

    return LedgerReconcileResult(rows=rows)


# ========= 导出台账 CSV =========
def _apply_common_filters_rows(
    rows_stmt, payload: LedgerQuery, time_from: datetime, time_to: datetime
):
    """
    出口（export）共用的过滤逻辑：
    - 使用与明细查询一致的条件（基于 occurred_at）。
    """
    conditions = _build_common_filters(payload, time_from, time_to)

    if conditions:
        rows_stmt = rows_stmt.where(sa.and_(*conditions))
    return rows_stmt


async def _exec_rows(session: AsyncSession, rows_stmt, payload: LedgerQuery) -> list[StockLedger]:
    rows_stmt = (
        rows_stmt.order_by(StockLedger.occurred_at.desc(), StockLedger.id.desc())
        .limit(payload.limit)
        .offset(payload.offset)
    )
    return (await session.execute(rows_stmt)).scalars().all()


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
    time_from, time_to = _normalize_time_range(payload)

    rows_stmt = select(StockLedger)
    rows_stmt = _apply_common_filters_rows(rows_stmt, payload, time_from, time_to)
    rows = await _exec_rows(session, rows_stmt, payload)

    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "delta", "reason", "ref", "occurred_at", "created_at", "after_qty"])
    for r in rows:
        ts_occ = (
            r.occurred_at.isoformat() if isinstance(r.occurred_at, datetime) else str(r.occurred_at)
        )
        ts_crt = (
            r.created_at.isoformat() if isinstance(r.created_at, datetime) else str(r.created_at)
        )
        writer.writerow(
            [r.id, r.delta, r.reason, r.ref or "", ts_occ, ts_crt, r.after_qty],
        )

    buf.seek(0)
    filename = f"stock_ledger_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        buf,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
