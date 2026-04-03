from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.inbound.contracts.inbound_atomic import (
    InboundAtomicCreateIn,
    InboundAtomicCreateOut,
    InboundAtomicResultRow,
)
from app.wms.inbound.repos.inbound_stock_write_repo import apply_inbound_stock
from app.wms.inbound.repos.item_lookup_repo import get_item_by_id
from app.wms.inbound.repos.lot_resolve_repo import resolve_inbound_lot


UTC = timezone.utc


@dataclass(slots=True)
class ResolvedInboundLine:
    """
    原子入库内部解析结果。
    """

    item_id: int
    barcode: str | None
    qty: int
    ref_line: int | None = None
    lot_code: str | None = None
    production_date: datetime | None = None
    expiry_date: datetime | None = None


async def _resolve_lines(
    session: AsyncSession,
    payload: InboundAtomicCreateIn,
) -> list[ResolvedInboundLine]:
    """
    解析入库行。

    当前阶段：
    - 仅支持 item_id
    - barcode-only 仍未实现
    """
    _ = session

    resolved: list[ResolvedInboundLine] = []
    for line in payload.lines:
        if line.item_id is None:
            raise NotImplementedError("barcode-only resolution is not implemented yet")

        resolved.append(
            ResolvedInboundLine(
                item_id=int(line.item_id),
                barcode=line.barcode,
                qty=int(line.qty),
                ref_line=int(line.ref_line) if line.ref_line is not None else None,
                lot_code=line.lot_code,
                production_date=(
                    datetime.combine(line.production_date, datetime.min.time(), tzinfo=UTC)
                    if line.production_date is not None
                    else None
                ),
                expiry_date=(
                    datetime.combine(line.expiry_date, datetime.min.time(), tzinfo=UTC)
                    if line.expiry_date is not None
                    else None
                ),
            )
        )

    return resolved


async def _apply_inbound_lines(
    session: AsyncSession,
    *,
    warehouse_id: int,
    lines: Sequence[ResolvedInboundLine],
    source_type: str,
    source_biz_type: str | None,
    source_ref: str | None,
    remark: str | None,
    trace_id: str,
) -> list[InboundAtomicResultRow]:
    """
    执行原子入库。

    第一阶段最小 happy path：
    - 仅支持 item_id
    - lot 解析/创建通过 repo 包装
    - stock/ledger 写入通过 repo 包装
    """
    rows: list[InboundAtomicResultRow] = []

    for idx, line in enumerate(lines, start=1):
        item = await get_item_by_id(session, item_id=int(line.item_id))
        if item is None:
            raise HTTPException(status_code=422, detail=f"item_not_found:{line.item_id}")

        lot_id = await resolve_inbound_lot(
            session,
            warehouse_id=int(warehouse_id),
            item=item,
            lot_code=line.lot_code,
        )

        ref = source_ref or trace_id
        ref_line = int(line.ref_line) if line.ref_line is not None else int(idx)

        await apply_inbound_stock(
            session,
            warehouse_id=int(warehouse_id),
            item_id=int(line.item_id),
            lot_id=int(lot_id),
            qty=int(line.qty),
            ref=str(ref),
            ref_line=ref_line,
            occurred_at=datetime.now(UTC),
            batch_code=line.lot_code,
            trace_id=trace_id,
            source_type=source_type,
            source_biz_type=source_biz_type,
            source_ref=source_ref,
            remark=remark,
        )

        rows.append(
            InboundAtomicResultRow(
                item_id=int(line.item_id),
                barcode=line.barcode,
                qty=int(line.qty),
                lot_id=int(lot_id),
                lot_code=line.lot_code,
            )
        )

    return rows


async def create_inbound_atomic(
    session: AsyncSession,
    payload: InboundAtomicCreateIn,
) -> InboundAtomicCreateOut:
    """
    WMS 原子入库入口。

    目标：
    - 不依赖采购单存在
    - 只依赖 WMS 核心事实：仓库、商品、数量、lot/效期、来源
    - 上游业务单据只通过 source_type/source_biz_type/source_ref 附带进入
    """
    trace_id = f"IN-ATOMIC-{uuid4().hex[:20]}"

    resolved_lines = await _resolve_lines(session, payload)

    rows = await _apply_inbound_lines(
        session,
        warehouse_id=int(payload.warehouse_id),
        lines=resolved_lines,
        source_type=payload.source_type,
        source_biz_type=payload.source_biz_type,
        source_ref=payload.source_ref,
        remark=payload.remark,
        trace_id=trace_id,
    )

    return InboundAtomicCreateOut(
        ok=True,
        warehouse_id=int(payload.warehouse_id),
        source_type=payload.source_type,
        source_biz_type=payload.source_biz_type,
        source_ref=payload.source_ref,
        trace_id=trace_id,
        rows=rows,
    )


__all__ = [
    "ResolvedInboundLine",
    "create_inbound_atomic",
]
