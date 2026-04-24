from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from fastapi import HTTPException
from sqlalchemy import text

from app.wms.inbound.contracts.inbound_commit import InboundCommitIn
from app.wms.inbound.services.inbound_commit_service import commit_inbound
from app.wms.inventory_adjustment.inbound_reversal.contracts.inbound_reversal import (
    InboundReversalIn,
)
from app.wms.inventory_adjustment.inbound_reversal.services.inbound_reversal_service import (
    reverse_inbound_event,
)


async def _pick_seed_item_uom(session):
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
              i.lot_source_policy::text AS lot_source_policy,
              i.expiry_policy::text AS expiry_policy
            FROM item_uoms u
            JOIN items i
              ON i.id = u.item_id
            ORDER BY
              CASE
                WHEN i.lot_source_policy::text IN ('SUPPLIER_ONLY', 'SUPPLIER') THEN 0
                ELSE 1
              END,
              u.id ASC
            LIMIT 1
            """
        )
    )
    picked = row.mappings().first()
    assert picked is not None, "expected seeded item_uoms to exist"

    return {
        "warehouse_id": int(warehouse_id),
        "item_id": int(picked["item_id"]),
        "uom_id": int(picked["uom_id"]),
        "lot_source_policy": str(picked["lot_source_policy"] or "INTERNAL_ONLY"),
        "expiry_policy": str(picked["expiry_policy"] or "NONE"),
    }


async def _load_event(session, *, event_id: int):
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


async def _load_ledger_by_event(session, *, event_id: int):
    row = await session.execute(
        text(
            """
            SELECT
              id,
              event_id,
              trace_id,
              ref,
              ref_line,
              warehouse_id,
              item_id,
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


def _date_to_utc_datetime(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


async def _insert_frozen_count_doc(
    session,
    *,
    warehouse_id: int,
) -> tuple[int, str, datetime]:
    snapshot_at = datetime.now(timezone.utc)
    count_no = f"UT-CNT-FROZEN-IN-{warehouse_id}-{int(snapshot_at.timestamp() * 1_000_000)}"
    row = await session.execute(
        text(
            """
            INSERT INTO count_docs (
              count_no,
              warehouse_id,
              snapshot_at,
              status,
              remark
            )
            VALUES (
              :count_no,
              :warehouse_id,
              :snapshot_at,
              'FROZEN',
              :remark
            )
            RETURNING id
            """
        ),
        {
            "count_no": count_no,
            "warehouse_id": int(warehouse_id),
            "snapshot_at": snapshot_at,
            "remark": "ut inbound reversal freeze guard",
        },
    )
    doc_id = int(row.scalar_one())
    await session.flush()
    return doc_id, count_no, snapshot_at


def test_inbound_reversal_operator_name_snapshot_required() -> None:
    with pytest.raises(ValidationError):
        InboundReversalIn(remark="missing operator")

    with pytest.raises(ValidationError):
        InboundReversalIn(operator_name_snapshot="   ", remark="blank operator")


@pytest.mark.asyncio
async def test_inbound_reversal_creates_reversal_event_and_supersedes_original(session):
    picked = await _pick_seed_item_uom(session)

    warehouse_id = int(picked["warehouse_id"])
    item_id = int(picked["item_id"])
    uom_id = int(picked["uom_id"])
    lot_source_policy = str(picked["lot_source_policy"])

    qty_input = 3
    production_date = date.today()
    expiry_date = production_date + timedelta(days=30)

    lot_code_input = None
    if lot_source_policy in {"SUPPLIER_ONLY", "SUPPLIER"}:
        lot_code_input = f"UT-IN-REV-{item_id}-{uom_id}"

    payload = InboundCommitIn.model_validate(
        {
            "warehouse_id": warehouse_id,
            "source_type": "MANUAL",
            "source_ref": None,
            "occurred_at": production_date.isoformat() + "T00:00:00Z",
            "remark": "ut inbound reversal source",
            "lines": [
                {
                    "item_id": item_id,
                    "uom_id": uom_id,
                    "qty_input": qty_input,
                    "lot_code_input": lot_code_input,
                    "production_date": production_date.isoformat(),
                    "expiry_date": expiry_date.isoformat(),
                    "remark": "ut source line",
                }
            ],
        }
    )

    original = await commit_inbound(session, payload=payload, user_id=None)
    assert original.ok is True
    assert int(original.event_id) > 0
    assert len(original.rows) == 1

    reversal = await reverse_inbound_event(
        session,
        event_id=int(original.event_id),
        payload=InboundReversalIn(
            occurred_at=_date_to_utc_datetime(production_date),
            operator_name_snapshot="测试操作人A",
            remark="ut inbound reversal",
        ),
        user_id=None,
    )

    assert reversal.ok is True
    assert int(reversal.target_event_id) == int(original.event_id)
    assert int(reversal.event_id) > int(original.event_id)
    assert reversal.source_type == original.source_type
    assert reversal.warehouse_id == original.warehouse_id
    assert len(reversal.rows) == 1

    original_event = await _load_event(session, event_id=int(original.event_id))
    reversal_event = await _load_event(session, event_id=int(reversal.event_id))
    assert original_event is not None
    assert reversal_event is not None

    assert str(original_event["event_kind"]) == "COMMIT"
    assert str(original_event["status"]) == "SUPERSEDED"

    assert str(reversal_event["event_type"]) == "INBOUND"
    assert str(reversal_event["event_kind"]) == "REVERSAL"
    assert str(reversal_event["status"]) == "COMMITTED"
    assert int(reversal_event["target_event_id"]) == int(original.event_id)

    orig_ledger = await _load_ledger_by_event(session, event_id=int(original.event_id))
    rev_ledger = await _load_ledger_by_event(session, event_id=int(reversal.event_id))
    assert orig_ledger is not None
    assert rev_ledger is not None

    assert str(orig_ledger["reason"]) == "RECEIPT"
    assert str(orig_ledger["sub_reason"]) in {"INBOUND_OPERATION", "ATOMIC_INBOUND"}

    assert str(rev_ledger["reason"]) == "ADJUSTMENT"
    assert str(rev_ledger["reason_canon"]) == "ADJUSTMENT"
    assert str(rev_ledger["sub_reason"]) == "INBOUND_REVERSAL"

    assert int(rev_ledger["item_id"]) == int(orig_ledger["item_id"])
    assert int(rev_ledger["warehouse_id"]) == int(orig_ledger["warehouse_id"])
    assert int(rev_ledger["lot_id"]) == int(orig_ledger["lot_id"])
    assert int(rev_ledger["delta"]) == -int(orig_ledger["delta"])


@pytest.mark.asyncio
async def test_inbound_reversal_duplicate_returns_already_reversed(session):
    picked = await _pick_seed_item_uom(session)

    warehouse_id = int(picked["warehouse_id"])
    item_id = int(picked["item_id"])
    uom_id = int(picked["uom_id"])
    lot_source_policy = str(picked["lot_source_policy"])

    qty_input = 2
    production_date = date.today()
    expiry_date = production_date + timedelta(days=30)

    lot_code_input = None
    if lot_source_policy in {"SUPPLIER_ONLY", "SUPPLIER"}:
        lot_code_input = f"UT-IN-REV-DUP-{item_id}-{uom_id}"

    payload = InboundCommitIn.model_validate(
        {
            "warehouse_id": warehouse_id,
            "source_type": "MANUAL",
            "source_ref": None,
            "occurred_at": production_date.isoformat() + "T00:00:00Z",
            "remark": "ut inbound reversal duplicate source",
            "lines": [
                {
                    "item_id": item_id,
                    "uom_id": uom_id,
                    "qty_input": qty_input,
                    "lot_code_input": lot_code_input,
                    "production_date": production_date.isoformat(),
                    "expiry_date": expiry_date.isoformat(),
                    "remark": "ut duplicate source line",
                }
            ],
        }
    )

    original = await commit_inbound(session, payload=payload, user_id=None)

    first = await reverse_inbound_event(
        session,
        event_id=int(original.event_id),
        payload=InboundReversalIn(
            operator_name_snapshot="测试操作人B",
            remark="ut first reversal",
        ),
        user_id=None,
    )
    assert first.ok is True

    with pytest.raises(HTTPException) as exc:
        await reverse_inbound_event(
            session,
            event_id=int(original.event_id),
            payload=InboundReversalIn(
                operator_name_snapshot="测试操作人C",
                remark="ut duplicate reversal",
            ),
            user_id=None,
        )

    assert exc.value.status_code == 409
    assert str(exc.value.detail).startswith("inbound_event_already_reversed:")


@pytest.mark.asyncio
async def test_inbound_reversal_rejects_when_count_doc_frozen(session):
    picked = await _pick_seed_item_uom(session)

    warehouse_id = int(picked["warehouse_id"])
    item_id = int(picked["item_id"])
    uom_id = int(picked["uom_id"])
    lot_source_policy = str(picked["lot_source_policy"])

    qty_input = 2
    production_date = date.today()
    expiry_date = production_date + timedelta(days=30)

    lot_code_input = None
    if lot_source_policy in {"SUPPLIER_ONLY", "SUPPLIER"}:
        lot_code_input = f"UT-IN-REV-FROZEN-{item_id}-{uom_id}"

    payload = InboundCommitIn.model_validate(
        {
            "warehouse_id": warehouse_id,
            "source_type": "MANUAL",
            "source_ref": None,
            "occurred_at": production_date.isoformat() + "T00:00:00Z",
            "remark": "ut inbound reversal frozen source",
            "lines": [
                {
                    "item_id": item_id,
                    "uom_id": uom_id,
                    "qty_input": qty_input,
                    "lot_code_input": lot_code_input,
                    "production_date": production_date.isoformat(),
                    "expiry_date": expiry_date.isoformat(),
                    "remark": "ut frozen source line",
                }
            ],
        }
    )

    original = await commit_inbound(session, payload=payload, user_id=None)
    doc_id, count_no, snapshot_at = await _insert_frozen_count_doc(
        session,
        warehouse_id=warehouse_id,
    )

    with pytest.raises(HTTPException) as exc:
        await reverse_inbound_event(
            session,
            event_id=int(original.event_id),
            payload=InboundReversalIn(
                operator_name_snapshot="测试操作人D",
                remark="ut frozen reversal",
            ),
            user_id=None,
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail
    assert isinstance(detail, dict), detail
    assert detail["error_code"] == "count_doc_frozen_for_warehouse"
    assert int(detail["warehouse_id"]) == warehouse_id
    assert int(detail["count_doc_id"]) == doc_id
    assert str(detail["count_no"]) == count_no
    assert str(detail["snapshot_at"]) == snapshot_at.isoformat()
