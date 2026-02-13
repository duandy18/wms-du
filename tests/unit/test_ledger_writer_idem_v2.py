# tests/unit/test_ledger_writer_idem_v2.py
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ledger_writer import write_ledger

UTC = timezone.utc


@pytest.mark.asyncio
async def test_write_ledger_idempotent(session: AsyncSession):
    # 先给 stocks 插个槽位并赋量（统一写 qty）
    await session.execute(
        text(
            """
        INSERT INTO stocks(item_id, warehouse_id, batch_code, qty)
        VALUES (3003, 1, 'IDEM', 5)
        ON CONFLICT ON CONSTRAINT uq_stocks_item_wh_batch DO UPDATE SET qty = EXCLUDED.qty
    """
        )
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
    )
    assert id2 == 0
