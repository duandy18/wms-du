from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Sequence
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.inbound.contracts.inbound_atomic import (
    InboundAtomicCreateIn,
    InboundAtomicCreateOut,
    InboundAtomicResultRow,
)
from app.wms.inbound.models.inbound_event import InboundEventLine, WmsEvent
from app.wms.inbound.repos.inbound_stock_write_repo import apply_inbound_stock
from app.wms.inbound.repos.item_lookup_repo import get_item_policy_by_id
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
    production_date: date | None = None
    expiry_date: date | None = None


def _new_trace_id() -> str:
    return f"IN-ATOMIC-{uuid4().hex[:20]}"


def _new_event_no() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"IA-{stamp}-{uuid4().hex[:8].upper()}"


def _map_atomic_source_to_event_source_type(*, source_type: str, source_biz_type: str | None) -> str:
    """
    将旧 atomic source 语义映射到统一事件头 wms_events.source_type。
    """
    st = str(source_type or "").strip().lower()
    sbt = str(source_biz_type or "").strip().lower()

    if st == "direct":
        if sbt in {"manual_adjust", "adjust_in", "inventory_adjust_in"}:
            return "ADJUST_IN"
        return "MANUAL"

    if st == "upstream":
        if sbt in {"purchase_receipt_confirm", "purchase", "purchase_order"}:
            return "PURCHASE_ORDER"
        if sbt in {"return", "return_in", "return_receipt", "rma_return"}:
            return "RETURN"
        if sbt in {"transfer_in", "transfer"}:
            return "TRANSFER_IN"
        if sbt in {"adjust_in"}:
            return "ADJUST_IN"
        return "MANUAL"

    return "MANUAL"


async def _require_base_uom_snapshot(
    session: AsyncSession,
    *,
    item_id: int,
) -> tuple[int, int]:
    """
    atomic inbound 当前仍按 base 数量语义解释 qty。
    为了不制造语义漂移，这里强制选 base uom，并要求 ratio_to_base = 1。
    """
    row = await session.execute(
        text(
            """
            SELECT id, ratio_to_base
            FROM item_uoms
            WHERE item_id = :item_id
              AND is_base = true
            ORDER BY id ASC
            LIMIT 1
            """
        ),
        {"item_id": int(item_id)},
    )
    m = row.mappings().first()

    if m is None:
        row2 = await session.execute(
            text(
                """
                SELECT id, ratio_to_base
                FROM item_uoms
                WHERE item_id = :item_id
                ORDER BY
                  CASE
                    WHEN is_inbound_default = true THEN 0
                    WHEN is_base = true THEN 1
                    ELSE 2
                  END,
                  id ASC
                LIMIT 1
                """
            ),
            {"item_id": int(item_id)},
        )
        m = row2.mappings().first()

    if m is None:
        raise HTTPException(status_code=422, detail=f"base_uom_unresolved:item={int(item_id)}")

    uom_id = int(m["id"])
    ratio = int(m["ratio_to_base"] or 0)

    if ratio <= 0:
        raise HTTPException(status_code=422, detail=f"invalid_ratio_to_base:item={int(item_id)}")
    if ratio != 1:
        raise HTTPException(
            status_code=422,
            detail=f"atomic_qty_requires_base_uom:item={int(item_id)}",
        )

    return uom_id, ratio


async def _call_apply_inbound_stock_compat(
    session: AsyncSession | None,
    *,
    warehouse_id: int,
    item_id: int,
    lot_id: int,
    qty: int,
    ref: str,
    ref_line: int,
    occurred_at: datetime,
    batch_code: str | None,
    production_date: date | None,
    expiry_date: date | None,
    event_id: int | None,
    trace_id: str,
    source_type: str,
    source_biz_type: str | None,
    source_ref: str | None,
    remark: str | None,
) -> None:
    """
    兼容旧测试 monkeypatch：
    - 真实 repo 已支持 event_id
    - 若旧 fake_apply_inbound_stock 尚未接 event_id，则退回不带 event_id 的调用
    """
    kwargs = {
        "warehouse_id": int(warehouse_id),
        "item_id": int(item_id),
        "lot_id": int(lot_id),
        "qty": int(qty),
        "ref": str(ref),
        "ref_line": int(ref_line),
        "occurred_at": occurred_at,
        "batch_code": batch_code,
        "production_date": production_date,
        "expiry_date": expiry_date,
        "event_id": int(event_id) if event_id is not None else None,
        "trace_id": str(trace_id),
        "source_type": str(source_type),
        "source_biz_type": source_biz_type,
        "source_ref": source_ref,
        "remark": remark,
    }

    try:
        await apply_inbound_stock(session, **kwargs)
    except TypeError as exc:
        if "event_id" not in str(exc):
            raise
        kwargs.pop("event_id", None)
        await apply_inbound_stock(session, **kwargs)


async def _resolve_lines(
    session: AsyncSession | None,
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
                production_date=line.production_date,
                expiry_date=line.expiry_date,
            )
        )

    return resolved


async def _apply_inbound_lines(
    session: AsyncSession | None,
    *,
    warehouse_id: int,
    lines: Sequence[ResolvedInboundLine],
    source_type: str,
    source_biz_type: str | None,
    source_ref: str | None,
    remark: str | None,
    event_id: int | None,
    occurred_at: datetime,
    trace_id: str,
) -> list[InboundAtomicResultRow]:
    """
    执行原子入库。

    当前阶段：
    - 真实路径：复用 lot resolve + stock/ledger 写入链，并补建统一事件行
    - mock 路径（session is None）：只做单测兼容，不持久化事件头/事件行
    """
    rows: list[InboundAtomicResultRow] = []

    for idx, line in enumerate(lines, start=1):
        item_policy = await get_item_policy_by_id(session, item_id=int(line.item_id))
        if item_policy is None:
            raise HTTPException(status_code=422, detail=f"item_not_found:{line.item_id}")

        lot_id = await resolve_inbound_lot(
            session,
            warehouse_id=int(warehouse_id),
            item_policy=item_policy,
            lot_code=line.lot_code,
            production_date=line.production_date,
            expiry_date=line.expiry_date,
        )

        ref = source_ref or trace_id
        ref_line = int(line.ref_line) if line.ref_line is not None else int(idx)

        if session is not None:
            uom_id, ratio_to_base_snapshot = await _require_base_uom_snapshot(
                session,
                item_id=int(line.item_id),
            )

            event_line = InboundEventLine(
                event_id=int(event_id) if event_id is not None else 0,
                line_no=int(ref_line),
                item_id=int(line.item_id),
                uom_id=int(uom_id),
                barcode_input=line.barcode,
                qty_input=int(line.qty),
                ratio_to_base_snapshot=int(ratio_to_base_snapshot),
                qty_base=int(line.qty),
                lot_code_input=line.lot_code,
                production_date=line.production_date,
                expiry_date=line.expiry_date,
                lot_id=int(lot_id),
                po_line_id=None,
                remark=remark,
            )
            session.add(event_line)
            await session.flush()

        await _call_apply_inbound_stock_compat(
            session,
            warehouse_id=int(warehouse_id),
            item_id=int(line.item_id),
            lot_id=int(lot_id),
            qty=int(line.qty),
            ref=str(ref),
            ref_line=int(ref_line),
            occurred_at=occurred_at,
            batch_code=line.lot_code,
            production_date=line.production_date,
            expiry_date=line.expiry_date,
            event_id=int(event_id) if event_id is not None else None,
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
    session: AsyncSession | None,
    payload: InboundAtomicCreateIn,
) -> InboundAtomicCreateOut:
    """
    WMS 原子入库入口。

    目标：
    - 不依赖采购单存在
    - 只依赖 WMS 核心事实：仓库、商品、数量、lot/效期、来源
    - 上游业务单据只通过 source_type/source_biz_type/source_ref 附带进入

    当前补充：
    - 真实路径会补建统一事件头 wms_events
    - mock/单测兼容路径（session is None）不持久化事件头，只保留 trace 链路
    """
    trace_id = _new_trace_id()
    occurred_at = payload.occurred_at or datetime.now(UTC)
    resolved_lines = await _resolve_lines(session, payload)

    event_id: int | None = None
    event_no: str | None = None

    if session is not None:
        event_no = _new_event_no()

        event = WmsEvent(
            event_no=str(event_no),
            event_type="INBOUND",
            warehouse_id=int(payload.warehouse_id),
            source_type=_map_atomic_source_to_event_source_type(
                source_type=payload.source_type,
                source_biz_type=payload.source_biz_type,
            ),
            source_ref=payload.source_ref,
            occurred_at=occurred_at,
            trace_id=str(trace_id),
            event_kind="COMMIT",
            status="COMMITTED",
            created_by=None,
            remark=payload.remark,
        )
        session.add(event)
        await session.flush()
        event_id = int(event.id)

    rows = await _apply_inbound_lines(
        session,
        warehouse_id=int(payload.warehouse_id),
        lines=resolved_lines,
        source_type=payload.source_type,
        source_biz_type=payload.source_biz_type,
        source_ref=payload.source_ref,
        remark=payload.remark,
        event_id=event_id,
        occurred_at=occurred_at,
        trace_id=trace_id,
    )

    return InboundAtomicCreateOut(
        ok=True,
        warehouse_id=int(payload.warehouse_id),
        source_type=payload.source_type,
        source_biz_type=payload.source_biz_type,
        source_ref=payload.source_ref,
        event_id=event_id,
        event_no=event_no,
        trace_id=trace_id,
        rows=rows,
    )


__all__ = [
    "ResolvedInboundLine",
    "create_inbound_atomic",
]
