# tests/unit/test_ledger_writer_idem_v2.py
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ledger_writer import write_ledger

UTC = timezone.utc


@pytest.mark.asyncio
async def test_write_ledger_idempotent(session: AsyncSession):
    # Phase 4D：用 lots + stocks_lot 提供一个可解释的库存背景（不再写 legacy stocks）
    lot_row = (
        await session.execute(
            text(
                """
                INSERT INTO lots(
                    warehouse_id,
                    item_id,
                    lot_code_source,
                    lot_code,
                    production_date,
                    expiry_date,
                    expiry_source
                )
                VALUES (1, 3003, 'SUPPLIER', 'IDEM', CURRENT_DATE, CURRENT_DATE + INTERVAL '365 day', 'EXPLICIT')
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
