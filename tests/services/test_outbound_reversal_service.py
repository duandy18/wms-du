from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.inbound.contracts.inbound_commit import InboundCommitIn
from app.wms.inbound.models.inbound_event import WmsEvent
from app.wms.inbound.services.inbound_commit_service import commit_inbound
from app.wms.inventory_adjustment.outbound_reversal.contracts.outbound_reversal import (
    OutboundReversalIn,
)
from app.wms.inventory_adjustment.outbound_reversal.services.outbound_reversal_service import (
    reverse_outbound_event,
)
from app.wms.outbound.models.outbound_event import OutboundEventLine
from app.wms.outbound.repos.outbound_event_repo import (
    insert_outbound_stock_ledger,
    load_stocks_lot_for_update,
    update_stocks_lot_qty,
)


def _date_to_utc_datetime(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


async def _pick_seed_item_uom(session: AsyncSession) -> dict[str, object]:
    wh_row = await session.execute(
        text(
            """
            SELECT id
            FROM warehouses
            ORDER BY id ASC
            LIMIT 1
            """
        )
    )
    warehouse_id = wh_row.scalar_one()

    row = await session.execute(
        text(
            """
            SELECT
              i.id AS item_id,
              u.id AS uom_id,
              COALESCE(i.lot_source_policy::text, 'INTERNAL_ONLY') AS lot_source_policy,
              COALESCE(i.expiry_policy::text, 'NONE') AS expiry_policy
            FROM item_uoms u
            JOIN items i
              ON i.id = u.item_id
            ORDER BY
              CASE
                WHEN COALESCE(i.lot_source_policy::text, 'INTERNAL_ONLY') IN ('SUPPLIER_ONLY', 'SUPPLIER') THEN 0
                ELSE 1
              END,
              u.id ASC
            LIMIT 1
            """
        )
    )
    picked = row.mappings().first()
    if picked is None:
        raise RuntimeError("测试库没有 item_uoms 种子数据，无法运行 outbound reversal 测试")

    return {
        "warehouse_id": int(warehouse_id),
        "item_id": int(picked["item_id"]),
        "uom_id": int(picked["uom_id"]),
        "lot_source_policy": str(picked["lot_source_policy"] or "INTERNAL_ONLY"),
        "expiry_policy": str(picked["expiry_policy"] or "NONE"),
    }


async def _load_stocks_lot_qty(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    lot_id: int,
) -> int:
    row = await session.execute(
        text(
            """
            SELECT qty
            FROM stocks_lot
            WHERE item_id = :item_id
              AND warehouse_id = :warehouse_id
              AND lot_id = :lot_id
            LIMIT 1
            """
        ),
        {
            "item_id": int(item_id),
            "warehouse_id": int(warehouse_id),
            "lot_id": int(lot_id),
        },
    )
    qty = row.scalar_one_or_none()
    if qty is None:
        raise RuntimeError("未找到刚生成的 stocks_lot 槽位")
    return int(qty)


async def _seed_outbound_source_event(session: AsyncSession) -> dict[str, object]:
    picked = await _pick_seed_item_uom(session)

    warehouse_id = int(picked["warehouse_id"])
    item_id = int(picked["item_id"])
    uom_id = int(picked["uom_id"])
    lot_source_policy = str(picked["lot_source_policy"])
    expiry_policy = str(picked["expiry_policy"])

    occurred_at = datetime.now(timezone.utc)
    production_date = occurred_at.date()
    expiry_date = production_date + timedelta(days=30)

    lot_code_input = None
    if lot_source_policy in {"SUPPLIER_ONLY", "SUPPLIER"}:
        lot_code_input = f"UT-OUT-REV-{item_id}-{uom_id}-{uuid4().hex[:8].upper()}"

    inbound_payload = InboundCommitIn.model_validate(
        {
            "warehouse_id": warehouse_id,
            "source_type": "MANUAL",
            "source_ref": None,
            "occurred_at": occurred_at.isoformat(),
            "remark": "ut outbound reversal stock seed",
            "lines": [
                {
                    "item_id": item_id,
                    "uom_id": uom_id,
                    "qty_input": 5,
                    "lot_code_input": lot_code_input,
                    "production_date": production_date.isoformat() if expiry_policy != "NONE" else None,
                    "expiry_date": expiry_date.isoformat() if expiry_policy != "NONE" else None,
                    "remark": "ut outbound reversal inbound seed line",
                }
            ],
        }
    )

    inbound = await commit_inbound(session, payload=inbound_payload, user_id=None)
    if not inbound.rows:
        raise RuntimeError("入库造数失败：没有生成结果行")

    seeded_row = inbound.rows[0]
    lot_id = getattr(seeded_row, "lot_id", None)
    if lot_id is None:
        raise RuntimeError("入库造数失败：没有生成 lot_id")

    current_qty = await _load_stocks_lot_qty(
        session,
        item_id=item_id,
        warehouse_id=warehouse_id,
        lot_id=int(lot_id),
    )
    qty_outbound = 2 if current_qty >= 2 else 1
    if qty_outbound <= 0:
        raise RuntimeError("入库造数后库存不足，无法运行 outbound reversal 测试")

    event = WmsEvent(
        event_no=f"UT-OE-{uuid4().hex[:12].upper()}",
        event_type="OUTBOUND",
        warehouse_id=int(warehouse_id),
        source_type="MANUAL",
        source_ref=f"UT-MOB-{uuid4().hex[:10].upper()}",
        occurred_at=occurred_at,
        trace_id=f"UT-OUT-{uuid4().hex[:20]}",
        event_kind="COMMIT",
        status="COMMITTED",
        created_by=None,
        remark="ut outbound reversal source",
    )
    session.add(event)
    await session.flush()

    line = OutboundEventLine(
        event_id=int(event.id),
        ref_line=1,
        item_id=int(item_id),
        qty_outbound=int(qty_outbound),
        lot_id=int(lot_id),
        lot_code_snapshot=lot_code_input,
        order_line_id=None,
        manual_doc_line_id=1,
        item_name_snapshot="ut item",
        item_sku_snapshot="ut-sku",
        item_spec_snapshot="ut-spec",
        remark="ut outbound line",
    )
    session.add(line)
    await session.flush()

    slot_qty = await load_stocks_lot_for_update(
        session,
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        lot_id=int(lot_id),
    )
    if slot_qty is None:
        raise RuntimeError("未找到 stocks_lot 槽位，无法构造 outbound source event")
    if int(slot_qty) < int(qty_outbound):
        raise RuntimeError("库存不足，无法构造 outbound source event")

    after_qty = int(slot_qty) - int(qty_outbound)

    await insert_outbound_stock_ledger(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_id=int(lot_id),
        qty_outbound=int(qty_outbound),
        after_qty=int(after_qty),
        occurred_at=occurred_at,
        source_ref=str(event.source_ref),
        ref_line=1,
        trace_id=str(event.trace_id),
        event_id=int(event.id),
    )
    await update_stocks_lot_qty(
        session,
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        lot_id=int(lot_id),
        qty=int(after_qty),
    )

    return {
        "event_id": int(event.id),
        "event_no": str(event.event_no),
        "source_ref": str(event.source_ref),
        "trace_id": str(event.trace_id),
        "occurred_at": occurred_at,
        "warehouse_id": int(warehouse_id),
        "item_id": int(item_id),
        "lot_id": int(lot_id),
        "qty_outbound": int(qty_outbound),
    }


async def _load_event(session: AsyncSession, *, event_id: int):
    row = await session.execute(
        text(
            """
            SELECT
              id,
              event_no,
              event_type,
              warehouse_id,
              source_type,
              source_ref,
              trace_id,
              event_kind,
              target_event_id,
              status
            FROM wms_events
            WHERE id = :event_id
            """
        ),
        {"event_id": int(event_id)},
    )
    m = row.mappings().first()
    return dict(m) if m else None


async def _load_ledger_by_event(session: AsyncSession, *, event_id: int):
    row = await session.execute(
        text(
            """
            SELECT
              id,
              event_id,
              trace_id,
              ref,
              ref_line,
              item_id,
              warehouse_id,
              lot_id,
              delta,
              after_qty,
              reason,
              reason_canon,
              sub_reason
            FROM stock_ledger
            WHERE event_id = :event_id
            ORDER BY id ASC
            LIMIT 1
            """
        ),
        {"event_id": int(event_id)},
    )
    m = row.mappings().first()
    return dict(m) if m else None


@pytest.mark.asyncio
async def test_outbound_reversal_creates_reversal_event_and_supersedes_original(session: AsyncSession):
    original = await _seed_outbound_source_event(session)

    reversal = await reverse_outbound_event(
        session,
        event_id=int(original["event_id"]),
        payload=OutboundReversalIn(remark="ut outbound reversal"),
        user_id=None,
    )

    assert reversal.ok is True
    assert int(reversal.target_event_id) == int(original["event_id"])
    assert int(reversal.event_id) > int(original["event_id"])
    assert reversal.source_type == "MANUAL"
    assert reversal.warehouse_id == int(original["warehouse_id"])
    assert len(reversal.rows) == 1

    original_event = await _load_event(session, event_id=int(original["event_id"]))
    reversal_event = await _load_event(session, event_id=int(reversal.event_id))
    assert original_event is not None
    assert reversal_event is not None

    assert str(original_event["event_kind"]) == "COMMIT"
    assert str(original_event["status"]) == "SUPERSEDED"

    assert str(reversal_event["event_type"]) == "OUTBOUND"
    assert str(reversal_event["event_kind"]) == "REVERSAL"
    assert str(reversal_event["status"]) == "COMMITTED"
    assert int(reversal_event["target_event_id"]) == int(original["event_id"])

    orig_ledger = await _load_ledger_by_event(session, event_id=int(original["event_id"]))
    rev_ledger = await _load_ledger_by_event(session, event_id=int(reversal.event_id))
    assert orig_ledger is not None
    assert rev_ledger is not None

    assert str(orig_ledger["reason"]) == "OUTBOUND_SHIP"
    assert str(orig_ledger["reason_canon"]) == "OUTBOUND"
    assert str(orig_ledger["sub_reason"]) == "ORDER_OUTBOUND"

    assert str(rev_ledger["reason"]) == "ADJUSTMENT"
    assert str(rev_ledger["reason_canon"]) == "ADJUSTMENT"
    assert str(rev_ledger["sub_reason"]) == "OUTBOUND_REVERSAL"

    assert int(rev_ledger["item_id"]) == int(orig_ledger["item_id"])
    assert int(rev_ledger["warehouse_id"]) == int(orig_ledger["warehouse_id"])
    assert int(rev_ledger["lot_id"]) == int(orig_ledger["lot_id"])
    assert int(rev_ledger["delta"]) == -int(orig_ledger["delta"])


@pytest.mark.asyncio
async def test_outbound_reversal_duplicate_returns_already_reversed(session: AsyncSession):
    original = await _seed_outbound_source_event(session)

    first = await reverse_outbound_event(
        session,
        event_id=int(original["event_id"]),
        payload=OutboundReversalIn(remark="ut first outbound reversal"),
        user_id=None,
    )
    assert first.ok is True

    with pytest.raises(HTTPException) as exc:
        await reverse_outbound_event(
            session,
            event_id=int(original["event_id"]),
            payload=OutboundReversalIn(remark="ut duplicate outbound reversal"),
            user_id=None,
        )

    assert exc.value.status_code == 409
    assert str(exc.value.detail).startswith("outbound_event_already_reversed:")
