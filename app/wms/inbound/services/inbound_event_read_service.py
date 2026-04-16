# app/wms/inbound/services/inbound_event_read_service.py
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.inbound.contracts.inbound_event_read import (
    InboundEventDetailOut,
    InboundEventLineOut,
    InboundEventListOut,
    InboundEventSummaryOut,
)


def _norm_text(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _normalize_limit(limit: int | None) -> int:
    x = int(limit or 20)
    if x < 1:
        return 1
    if x > 200:
        return 200
    return x


def _normalize_offset(offset: int | None) -> int:
    x = int(offset or 0)
    if x < 0:
        return 0
    return x


def _build_event_filters(
    *,
    warehouse_id: int | None,
    source_type: str | None,
    source_ref: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> tuple[str, dict[str, Any]]:
    clauses = ["event_type = 'INBOUND'"]
    params: dict[str, Any] = {}

    if warehouse_id is not None:
        clauses.append("warehouse_id = :warehouse_id")
        params["warehouse_id"] = int(warehouse_id)

    norm_source_type = _norm_text(source_type)
    if norm_source_type is not None:
        clauses.append("source_type = :source_type")
        params["source_type"] = norm_source_type

    norm_source_ref = _norm_text(source_ref)
    if norm_source_ref is not None:
        clauses.append("source_ref = :source_ref")
        params["source_ref"] = norm_source_ref

    if date_from is not None:
        clauses.append("occurred_at >= :date_from")
        params["date_from"] = date_from

    if date_to is not None:
        clauses.append("occurred_at <= :date_to")
        params["date_to"] = date_to

    return " AND ".join(clauses), params


async def list_inbound_events(
    session: AsyncSession,
    *,
    warehouse_id: int | None = None,
    source_type: str | None = None,
    source_ref: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int | None = 20,
    offset: int | None = 0,
) -> InboundEventListOut:
    """
    入库事件列表。

    当前目标：
    - 直接以 wms_events 为真相源
    - 不混入旧 receipt/task 语义
    - 仅返回前端工作台下卡所需的事件头摘要
    """
    limit_n = _normalize_limit(limit)
    offset_n = _normalize_offset(offset)

    where_sql, params = _build_event_filters(
        warehouse_id=warehouse_id,
        source_type=source_type,
        source_ref=source_ref,
        date_from=date_from,
        date_to=date_to,
    )

    total_sql = text(
        f"""
        SELECT COUNT(*) AS total
          FROM wms_events
         WHERE {where_sql}
        """
    )
    total_row = await session.execute(total_sql, params)
    total = int(total_row.scalar_one() or 0)

    list_sql = text(
        f"""
        SELECT
            id AS event_id,
            event_no,
            event_type,
            warehouse_id,
            source_type,
            source_ref,
            occurred_at,
            committed_at,
            trace_id,
            event_kind,
            status,
            remark
          FROM wms_events
         WHERE {where_sql}
         ORDER BY occurred_at DESC, id DESC
         LIMIT :limit
        OFFSET :offset
        """
    )
    rows = await session.execute(
        list_sql,
        {
            **params,
            "limit": limit_n,
            "offset": offset_n,
        },
    )

    items = [
        InboundEventSummaryOut.model_validate(dict(r))
        for r in rows.mappings().all()
    ]

    return InboundEventListOut(
        total=total,
        items=items,
    )


async def get_inbound_event_detail(
    session: AsyncSession,
    *,
    event_id: int,
) -> InboundEventDetailOut:
    """
    入库事件详情。

    当前目标：
    - event 头来自 wms_events
    - line 明细来自 inbound_event_lines
    - 展示字段通过 items / item_uoms / lots 补齐
    """
    event_sql = text(
        """
        SELECT
            id AS event_id,
            event_no,
            event_type,
            warehouse_id,
            source_type,
            source_ref,
            occurred_at,
            committed_at,
            trace_id,
            event_kind,
            status,
            remark
          FROM wms_events
         WHERE id = :event_id
           AND event_type = 'INBOUND'
         LIMIT 1
        """
    )
    event_row = await session.execute(event_sql, {"event_id": int(event_id)})
    event_map = event_row.mappings().first()
    if event_map is None:
        raise HTTPException(
            status_code=404,
            detail=f"入库事件不存在：event_id={int(event_id)}",
        )

    lines_sql = text(
        """
        SELECT
            iel.line_no,
            iel.item_id,
            it.name AS item_name,
            it.sku AS item_sku,
            iel.uom_id,
            COALESCE(NULLIF(iu.display_name, ''), iu.uom) AS uom_name,
            iel.barcode_input,
            iel.qty_input,
            iel.ratio_to_base_snapshot,
            iel.qty_base,
            iel.lot_id,
            iel.lot_code_input,
            lo.lot_code,
            iel.production_date,
            iel.expiry_date,
            iel.po_line_id,
            iel.remark
          FROM inbound_event_lines AS iel
          LEFT JOIN items AS it
            ON it.id = iel.item_id
          LEFT JOIN item_uoms AS iu
            ON iu.id = iel.uom_id
          LEFT JOIN lots AS lo
            ON lo.id = iel.lot_id
         WHERE iel.event_id = :event_id
         ORDER BY iel.line_no ASC, iel.id ASC
        """
    )
    line_rows = await session.execute(lines_sql, {"event_id": int(event_id)})

    lines = [
        InboundEventLineOut.model_validate(dict(r))
        for r in line_rows.mappings().all()
    ]

    return InboundEventDetailOut(
        event=InboundEventSummaryOut.model_validate(dict(event_map)),
        lines=lines,
    )


__all__ = [
    "list_inbound_events",
    "get_inbound_event_detail",
]
