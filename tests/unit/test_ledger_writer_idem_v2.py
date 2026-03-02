# tests/unit/test_ledger_writer_idem_v2.py
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ledger_writer import write_ledger
from tests.utils.ensure_minimal import ensure_item

UTC = timezone.utc


@pytest.mark.asyncio
async def test_write_ledger_idempotent(session: AsyncSession):
    await ensure_item(session, id=3003, sku="SKU-3003", name="ITEM-3003", expiry_required=False)

    # lots 终态：不再承载 item_uom_snapshot / item_case_*_snapshot 等历史列
    # 也不依赖 ON CONFLICT 的具体 unique/index；先查再插最稳。
    row0 = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM lots
                 WHERE warehouse_id = 1
                   AND item_id = 3003
                   AND lot_code_source = 'SUPPLIER'
                   AND lot_code = 'IDEM'
                 LIMIT 1
                """
            )
        )
    ).first()

    if row0 is not None:
        lot_id = int(row0[0])
    else:
        lot_row = (
            await session.execute(
                text(
                    """
                    INSERT INTO lots(
                        warehouse_id,
                        item_id,
                        lot_code_source,
                        lot_code,
                        source_receipt_id,
                        source_line_no,
                        -- required snapshots (NOT NULL)
                        item_lot_source_policy_snapshot,
                        item_expiry_policy_snapshot,
                        item_derivation_allowed_snapshot,
                        item_uom_governance_enabled_snapshot,
                        -- optional snapshots (nullable)
                        item_shelf_life_value_snapshot,
                        item_shelf_life_unit_snapshot,
                        created_at
                    )
                    SELECT
                        1,
                        3003,
                        'SUPPLIER',
                        'IDEM',
                        NULL,
                        NULL,
                        it.lot_source_policy,
                        it.expiry_policy,
                        it.derivation_allowed,
                        it.uom_governance_enabled,
                        it.shelf_life_value,
                        it.shelf_life_unit,
                        now()
                      FROM items it
                     WHERE it.id = 3003
                    RETURNING id
                    """
                )
            )
        ).first()
        assert lot_row is not None
        lot_id = int(lot_row[0])

    await session.execute(
        text(
            """
            INSERT INTO stocks_lot(item_id, warehouse_id, lot_id, qty)
            VALUES (3003, 1, :lot_id, 5)
            ON CONFLICT ON CONSTRAINT uq_stocks_lot_item_wh_lot
            DO UPDATE SET qty = EXCLUDED.qty
            """
        ),
        {"lot_id": int(lot_id)},
    )

    id1 = await write_ledger(
        session,
        warehouse_id=1,
        item_id=3003,
        batch_code="IDEM",
        reason="COUNT",
        delta=1,
        after_qty=6,
        ref="LED-IDEM-1",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        lot_id=int(lot_id),
    )
    assert id1 > 0

    id2 = await write_ledger(
        session,
        warehouse_id=1,
        item_id=3003,
        batch_code="IDEM",
        reason="COUNT",
        delta=1,
        after_qty=6,
        ref="LED-IDEM-1",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        lot_id=int(lot_id),
    )
    assert id2 == 0
