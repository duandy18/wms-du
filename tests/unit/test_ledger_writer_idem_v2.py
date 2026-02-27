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
    # Phase 4D：用 lots + stocks_lot 提供一个可解释的库存背景（不再写 legacy stocks）

    # Phase M：items policy NOT NULL → 统一走最小合法 helper
    await ensure_item(session, id=3003, sku="SKU-3003", name="ITEM-3003", expiry_required=False)

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
                    production_date,
                    expiry_date,
                    expiry_source,
                    -- required snapshots (NOT NULL)
                    item_lot_source_policy_snapshot,
                    item_expiry_policy_snapshot,
                    item_derivation_allowed_snapshot,
                    item_uom_governance_enabled_snapshot,
                    -- optional snapshots (nullable)
                    item_has_shelf_life_snapshot,
                    item_shelf_life_value_snapshot,
                    item_shelf_life_unit_snapshot,
                    item_uom_snapshot,
                    item_case_ratio_snapshot,
                    item_case_uom_snapshot
                )
                SELECT
                    1,
                    3003,
                    'SUPPLIER',
                    'IDEM',
                    NULL,
                    NULL,
                    CURRENT_DATE,
                    CURRENT_DATE + INTERVAL '365 day',
                    'EXPLICIT',
                    it.lot_source_policy,
                    it.expiry_policy,
                    it.derivation_allowed,
                    it.uom_governance_enabled,
                    it.has_shelf_life,
                    it.shelf_life_value,
                    it.shelf_life_unit,
                    it.uom,
                    it.case_ratio,
                    it.case_uom
                  FROM items it
                 WHERE it.id = 3003
                ON CONFLICT (warehouse_id, item_id, lot_code_source, lot_code)
                WHERE lot_code_source = 'SUPPLIER'
                DO UPDATE SET expiry_date = EXCLUDED.expiry_date
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

    # 首次写
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

    # 幂等命中
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
