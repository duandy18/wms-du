from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service import StockService

UTC = timezone.utc


async def _qty(session: AsyncSession, item_id: int, wh: int, code: str) -> int:
    r = await session.execute(
        text("SELECT qty FROM stocks WHERE item_id=:i AND warehouse_id=:w AND batch_code=:c"),
        {"i": item_id, "w": wh, "c": code},
    )
    return int(r.scalar_one_or_none() or 0)


@pytest.mark.asyncio
async def test_outbound_core_idem_and_insufficient(session: AsyncSession):
    svc = StockService()
    item_id, wh, code = 3003, 1, "NEAR"
    before = await _qty(session, item_id, wh, code)
    assert before >= 1

    # 扣 1
    await svc.adjust(
        session=session,
        item_id=item_id,
        delta=-1,
        reason=MovementType.OUTBOUND,
        ref="Q-OUTCORE-1",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code=code,
        warehouse_id=wh,
    )
    mid = await _qty(session, item_id, wh, code)
    assert mid == before - 1

    # 同 ref/ref_line 幂等
    res = await svc.adjust(
        session=session,
        item_id=item_id,
        delta=-1,
        reason=MovementType.OUTBOUND,
        ref="Q-OUTCORE-1",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code=code,
        warehouse_id=wh,
    )
    assert res.get("idempotent") is True

    # 不足
    remain = await _qty(session, item_id, wh, code)
    with pytest.raises(ValueError):
        await svc.adjust(
            session=session,
            item_id=item_id,
            delta=-(remain + 1),
            reason=MovementType.OUTBOUND,
            ref="Q-OUTCORE-2",
            ref_line=1,
            occurred_at=datetime.now(UTC),
            batch_code=code,
            warehouse_id=wh,
        )
