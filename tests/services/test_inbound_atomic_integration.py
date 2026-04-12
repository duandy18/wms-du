from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text

from app.wms.inbound.contracts.inbound_atomic import InboundAtomicCreateIn
from app.wms.inbound.services.inbound_atomic_service import create_inbound_atomic
from tests.utils.ensure_minimal import ensure_item, ensure_warehouse, _get_stock_qty


async def _ensure_base_uom(
    session,
    *,
    item_id: int,
) -> int:
    row = await session.execute(
        text(
            """
            INSERT INTO item_uoms(
              item_id, uom, ratio_to_base, display_name,
              is_base, is_purchase_default, is_inbound_default, is_outbound_default
            )
            VALUES(
              :item_id, 'PCS', 1, 'PCS',
              TRUE, TRUE, TRUE, TRUE
            )
            ON CONFLICT ON CONSTRAINT uq_item_uoms_item_uom
            DO UPDATE SET
              ratio_to_base = EXCLUDED.ratio_to_base,
              display_name = EXCLUDED.display_name,
              is_base = EXCLUDED.is_base,
              is_purchase_default = EXCLUDED.is_purchase_default,
              is_inbound_default = EXCLUDED.is_inbound_default,
              is_outbound_default = EXCLUDED.is_outbound_default
            RETURNING id
            """
        ),
        {"item_id": int(item_id)},
    )
    uom_id = row.scalar_one_or_none()
    if uom_id is not None:
        return int(uom_id)

    row2 = await session.execute(
        text(
            """
            SELECT id
            FROM item_uoms
            WHERE item_id = :item_id
              AND is_base = true
            ORDER BY id ASC
            LIMIT 1
            """
        ),
        {"item_id": int(item_id)},
    )
    got = row2.scalar_one_or_none()
    assert got is not None, {"msg": "expected base uom after ensure", "item_id": int(item_id)}
    return int(got)


async def _load_event(
    session,
    *,
    event_id: int,
):
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
              trace_id
            FROM wms_events
            WHERE id = :event_id
            """
        ),
        {"event_id": int(event_id)},
    )
    m = row.mappings().first()
    return dict(m) if m else None


async def _load_ledger_row(
    session,
    *,
    ref: str,
    ref_line: int,
    item_id: int,
):
    row = await session.execute(
        text(
            """
            SELECT
              id,
              warehouse_id,
              item_id,
              lot_id,
              delta,
              reason,
              ref,
              ref_line,
              event_id,
              trace_id
              FROM stock_ledger
             WHERE ref = :ref
               AND ref_line = :ref_line
               AND item_id = :item_id
             ORDER BY id DESC
             LIMIT 1
            """
        ),
        {
            "ref": str(ref),
            "ref_line": int(ref_line),
            "item_id": int(item_id),
        },
    )
    m = row.mappings().first()
    return dict(m) if m else None


async def test_inbound_atomic_direct_single_line_happy_path(session):
    warehouse_id = 101
    item_id = 10001
    lot_code = "ATOMIC-IN-LOT-001"
    qty = 3

    await ensure_warehouse(session, id=warehouse_id, name=f"WH-{warehouse_id}")
    await ensure_item(
        session,
        id=item_id,
        sku=f"SKU-{item_id}",
        name=f"ITEM-{item_id}",
        expiry_required=True,
    )
    await _ensure_base_uom(session, item_id=item_id)

    prod = date.today()
    exp = prod + timedelta(days=30)

    payload = InboundAtomicCreateIn.model_validate(
        {
            "warehouse_id": warehouse_id,
            "source_type": "direct",
            "source_biz_type": "manual_adjust",
            "remark": "atomic inbound integration test",
            "lines": [
                {
                    "item_id": item_id,
                    "qty": qty,
                    "lot_code": lot_code,
                    "production_date": prod.isoformat(),
                    "expiry_date": exp.isoformat(),
                }
            ],
        }
    )

    out = await create_inbound_atomic(session, payload)

    assert out.ok is True
    assert out.warehouse_id == warehouse_id
    assert out.source_type == "direct"
    assert out.source_biz_type == "manual_adjust"
    assert out.source_ref is None
    assert out.event_id is not None
    assert str(out.event_no).startswith("IA-")
    assert out.trace_id.startswith("IN-ATOMIC-")
    assert len(out.rows) == 1

    event = await _load_event(session, event_id=int(out.event_id))
    assert event is not None
    assert int(event["id"]) == int(out.event_id)
    assert str(event["event_no"]) == str(out.event_no)
    assert str(event["event_type"]) == "INBOUND"
    assert int(event["warehouse_id"]) == warehouse_id
    assert str(event["source_type"]) == "ADJUST_IN"
    assert event["source_ref"] is None
    assert str(event["trace_id"]) == out.trace_id

    row = out.rows[0]
    assert row.item_id == item_id
    assert row.qty == qty
    assert row.lot_id is not None
    assert row.lot_code == lot_code

    stock_qty = await _get_stock_qty(
        session,
        item_id=item_id,
        warehouse_id=warehouse_id,
        lot_id=int(row.lot_id),
    )
    assert stock_qty == qty

    ledger_row = await _load_ledger_row(
        session,
        ref=out.trace_id,
        ref_line=1,
        item_id=item_id,
    )
    assert ledger_row is not None
    assert int(ledger_row["warehouse_id"]) == warehouse_id
    assert int(ledger_row["item_id"]) == item_id
    assert int(ledger_row["lot_id"]) == int(row.lot_id)
    assert int(ledger_row["delta"]) == qty
    assert str(ledger_row["ref"]) == out.trace_id
    assert int(ledger_row["ref_line"]) == 1
    assert int(ledger_row["event_id"]) == int(out.event_id)
    assert str(ledger_row["trace_id"]) == out.trace_id
