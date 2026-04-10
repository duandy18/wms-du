# app/wms/ledger/helpers/stock_ledger.py
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Tuple

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lot import Lot
from app.models.stock_ledger import StockLedger
from app.wms.ledger.contracts.stock_ledger import LedgerQuery
from app.wms.shared.services.lot_code_contract import normalize_optional_lot_code

# 仅用于 ledger 关键词过滤的轻量只读表映射：
# 先去掉对 PMS Item ORM 的直接依赖，不改 helper 的调用签名。
ITEMS_TABLE = sa.table(
    "items",
    sa.column("id"),
    sa.column("name"),
    sa.column("sku"),
)


def normalize_time_range(q: LedgerQuery) -> Tuple[datetime, datetime]:
    """
    规范化 time_from / time_to（用于常规查询 /query）：

    - 两者都为空：默认最近 7 天；
    - 只填了一个：自动补另一个；
    - 限制最大跨度 90 天，避免误查全库。

    重要边界处理：
    - 当用户只提供 time_from（time_to 为空 -> 视为 now）时，
      可能因“生成 time_from -> 发请求”间的时间漂移导致跨度略超过 90 天。
      此时不应直接报错，而应自动将 time_from 夹紧到 (time_to - 90 天)，确保合同 <=90 天。
    """
    now = datetime.now(timezone.utc)

    time_to = q.time_to or now
    time_from = q.time_from or (time_to - timedelta(days=7))

    # 统一时区（避免 naive/aware 混用）
    if time_from.tzinfo is None:
        time_from = time_from.replace(tzinfo=timezone.utc)
    if time_to.tzinfo is None:
        time_to = time_to.replace(tzinfo=timezone.utc)

    if time_to < time_from:
        raise HTTPException(status_code=400, detail="'time_to' must be >= 'time_from'")

    max_span = timedelta(days=90)
    span = time_to - time_from

    if span > max_span:
        # ✅ 只有在“开放区间”场景（只填 time_from 或只填 time_to）时做夹紧
        # - 只填 time_from：用户想查到现在，但不能超过 90 天 => 夹紧 time_from
        # - 只填 time_to：一般不会走到这里（默认 7 天），仍做保护性处理
        if q.time_from is not None and q.time_to is None:
            time_from = time_to - max_span
        elif q.time_to is not None and q.time_from is None:
            time_to = time_from + max_span
        else:
            # 两边都明确给了，说明用户意图就是这个跨度，直接报错
            raise HTTPException(
                status_code=400,
                detail="时间范围过大，请缩小到 90 天以内（<= 90 天）。",
            )

    return time_from, time_to


def _to_str_or_none(v) -> str | None:
    """
    将 Enum/str/None 统一为可用于 DB compare 的字符串：
    - None -> None
    - Enum -> str(Enum) == "ReasonCanon.RECEIPT" 这种不合适，所以用 .value 优先
    - str -> strip
    """
    if v is None:
        return None
    vv = getattr(v, "value", None)
    if isinstance(vv, str):
        x = vv.strip()
        return x or None
    if isinstance(v, str):
        x = v.strip()
        return x or None
    x = str(v).strip()
    return x or None


def build_common_filters(q: LedgerQuery, time_from: datetime, time_to: datetime):
    """
    根据查询模型构建 SQLAlchemy 过滤条件列表（不包含 item_keyword 模糊搜索）。

    注意：
    - reason：原始 reason（可能为 OUTBOUND_SHIP 等别名）
    - reason_canon：稳定口径（RECEIPT/SHIPMENT/ADJUSTMENT）
    - sub_reason：业务动作细分（PO_RECEIPT / ORDER_SHIP / COUNT_ADJUST 等）
    """
    conditions: list[sa.ColumnElement[bool]] = [
        StockLedger.occurred_at >= time_from,
        StockLedger.occurred_at <= time_to,
    ]

    if q.item_id is not None:
        conditions.append(StockLedger.item_id == q.item_id)

    if q.warehouse_id is not None:
        conditions.append(StockLedger.warehouse_id == q.warehouse_id)

    if getattr(q, "lot_id", None) is not None:
        conditions.append(StockLedger.lot_id == getattr(q, "lot_id"))

    fields_set = getattr(q, "model_fields_set", set())
    if "batch_code" in fields_set:
        norm_bc = normalize_optional_lot_code(getattr(q, "batch_code", None))
        if norm_bc is None:
            conditions.append(
                sa.exists(
                    select(1).select_from(Lot).where(
                        sa.and_(
                            Lot.id == StockLedger.lot_id,
                            Lot.lot_code.is_(None),
                        )
                    )
                )
            )
        else:
            conditions.append(
                sa.exists(
                    select(1).select_from(Lot).where(
                        sa.and_(
                            Lot.id == StockLedger.lot_id,
                            Lot.lot_code == norm_bc,
                        )
                    )
                )
            )

    if q.reason:
        conditions.append(StockLedger.reason == q.reason)

    rc = _to_str_or_none(getattr(q, "reason_canon", None))
    if rc:
        conditions.append(StockLedger.reason_canon == rc)

    sr = _to_str_or_none(getattr(q, "sub_reason", None))
    if sr:
        conditions.append(StockLedger.sub_reason == sr)

    if q.ref:
        x = str(q.ref).strip()
        if x:
            if ":" in x:
                base = x.split(":")[-1].strip()
                parts: list[sa.ColumnElement[bool]] = []
                parts.append(StockLedger.ref == x)
                if base and base != x:
                    parts.append(StockLedger.ref == base)
                    parts.append(StockLedger.ref.like(f"%:{base}"))
                conditions.append(sa.or_(*parts))
            else:
                conditions.append(sa.or_(StockLedger.ref == x, StockLedger.ref.like(f"%:{x}")))

    if q.trace_id:
        conditions.append(StockLedger.trace_id == q.trace_id)

    return conditions


def infer_movement_type(reason: str | None) -> str | None:
    if not reason:
        return None
    r = reason.upper()

    if r in {"RECEIPT", "INBOUND", "INBOUND_RECEIPT"}:
        return "INBOUND"

    if r in {"SHIP", "SHIPMENT", "OUTBOUND_SHIP", "OUTBOUND_COMMIT"}:
        return "OUTBOUND"

    if r in {"COUNT", "STOCK_COUNT", "INVENTORY_COUNT"}:
        return "COUNT"

    if r in {"ADJUSTMENT", "ADJUST", "MANUAL_ADJUST"}:
        return "ADJUST"

    if r in {"RETURN", "RMA", "INBOUND_RETURN"}:
        return "RETURN"

    return "UNKNOWN"


def build_base_ids_stmt(q: LedgerQuery, time_from: datetime, time_to: datetime):
    """
    按查询条件构造基础 SQL（只选中符合条件的 id 列表）：

    - 支持按 item_id / warehouse_id / lot_id / batch_code(展示码) / reason / reason_canon / sub_reason / ref / trace_id / 时间过滤；
    - 支持按 item_keyword 模糊匹配 items.name / items.sku；
    - 不再依赖 stock_id / batch_id，完全对齐当前 StockLedger 模型。

    当前阶段：
    - 先去掉对 PMS Item ORM 的直接依赖
    - 仍保持查询语义和 helper 签名不变
    """
    stmt = select(StockLedger.id).select_from(StockLedger)
    conditions = build_common_filters(q, time_from, time_to)

    if q.item_keyword:
        kw = f"%{q.item_keyword.strip()}%"
        stmt = stmt.join(ITEMS_TABLE, ITEMS_TABLE.c.id == StockLedger.item_id)
        conditions.append(
            sa.or_(
                ITEMS_TABLE.c.name.ilike(kw),
                ITEMS_TABLE.c.sku.ilike(kw),
            )
        )

    if conditions:
        stmt = stmt.where(sa.and_(*conditions))
    return stmt


def apply_common_filters_rows(rows_stmt, payload: LedgerQuery, time_from: datetime, time_to: datetime):
    """
    export 共用的过滤逻辑：
    - 使用与明细查询一致的条件（基于 occurred_at + 其它维度）。
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
        writer.writerow(
            [
                r.id,
                r.delta,
                r.reason,
                r.ref,
                r.occurred_at.isoformat() if getattr(r, "occurred_at", None) else "",
                r.created_at.isoformat() if getattr(r, "created_at", None) else "",
                r.after_qty,
            ]
        )
    filename = f"stock_ledger_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return buf, filename
