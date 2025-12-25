# app/api/routers/stock_ledger_helpers.py
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Tuple

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.stock_ledger import StockLedger
from app.schemas.stock_ledger import LedgerQuery


def normalize_time_range(q: LedgerQuery) -> Tuple[datetime, datetime]:
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


def build_common_filters(q: LedgerQuery, time_from: datetime, time_to: datetime):
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


def infer_movement_type(reason: str | None) -> str | None:
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

    return "UNKNOWN"


def build_base_ids_stmt(q: LedgerQuery, time_from: datetime, time_to: datetime):
    """
    按查询条件构造基础 SQL（只选中符合条件的 id 列表）：
    - 支持按 item_id / warehouse_id / batch_code / reason / ref / trace_id / 时间过滤；
    - 支持按 item_keyword 模糊匹配 items.name / items.sku；
    - 不再依赖 stock_id / batch_id，完全对齐当前 StockLedger 模型。
    """
    stmt = select(StockLedger.id).select_from(StockLedger)
    conditions = build_common_filters(q, time_from, time_to)

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


def apply_common_filters_rows(
    rows_stmt, payload: LedgerQuery, time_from: datetime, time_to: datetime
):
    """
    出口（export）共用的过滤逻辑：
    - 使用与明细查询一致的条件（基于 occurred_at）。
    """
    conditions = build_common_filters(payload, time_from, time_to)

    if conditions:
        rows_stmt = rows_stmt.where(sa.and_(*conditions))
    return rows_stmt


async def exec_rows(session: AsyncSession, rows_stmt, payload: LedgerQuery):
    rows_stmt = (
        rows_stmt.order_by(StockLedger.occurred_at.desc(), StockLedger.id.desc())
        .limit(payload.limit)
        .offset(payload.offset)
    )
    return (await session.execute(rows_stmt)).scalars().all()


def build_export_csv(rows) -> tuple[StringIO, str]:
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
        writer.writerow([r.id, r.delta, r.reason, r.ref or "", ts_occ, ts_crt, r.after_qty])

    buf.seek(0)
    filename = f"stock_ledger_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return buf, filename
