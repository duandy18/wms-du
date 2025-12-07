from datetime import date, datetime, timezone

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
async def test_receive_then_pick_then_count(session: AsyncSession):
    svc = StockService()
    # 1) 入库 +2（带日期约束）
    await svc.adjust(
        session=session,
        item_id=1,
        delta=2,
        reason=MovementType.INBOUND,
        ref="Q-IPC-1",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code="NEAR",
        production_date=date.today(),
        warehouse_id=1,
    )
    q1 = await _qty(session, 1, 1, "NEAR")
    assert q1 >= 2

    # 2) 拣货 -1（必须指定 batch）
    await svc.adjust(
        session=session,
        item_id=1,
        delta=-1,
        reason=MovementType.OUTBOUND,
        ref="Q-IPC-2",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code="NEAR",
        warehouse_id=1,
    )
    q2 = await _qty(session, 1, 1, "NEAR")
    assert q2 == q1 - 1

    # 3) 盘点：把数量调整为 1（delta = 1 - 当前）
    remain = await _qty(session, 1, 1, "NEAR")
    delta = 1 - remain
    if delta != 0:
        await svc.adjust(
            session=session,
            item_id=1,
            delta=delta,
            reason=MovementType.COUNT,
            ref="Q-IPC-3",
            ref_line=1,
            occurred_at=datetime.now(UTC),
            batch_code="NEAR",
            production_date=date.today(),
            warehouse_id=1,
        )
    q3 = await _qty(session, 1, 1, "NEAR")
    assert q3 == 1
