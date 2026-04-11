from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text

from app.wms.inbound.contracts.inbound_atomic import InboundAtomicCreateIn
from app.wms.inbound.services.inbound_atomic_service import create_inbound_atomic
from tests.utils.ensure_minimal import ensure_item, ensure_warehouse, _get_stock_qty


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
            SELECT id, warehouse_id, item_id, lot_id, delta, reason, ref, ref_line
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
    assert out.trace_id.startswith("IN-ATOMIC-")
    assert len(out.rows) == 1

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
