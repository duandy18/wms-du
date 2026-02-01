from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service import StockService

UTC = timezone.utc


async def _qty(session: AsyncSession, item_id: int, wh: int, code: str | None) -> int:
    r = await session.execute(
        text(
            """
            SELECT qty
              FROM stocks
             WHERE item_id=:i
               AND warehouse_id=:w
               AND batch_code IS NOT DISTINCT FROM :c
            """
        ),
        {"i": item_id, "w": wh, "c": code},
    )
    return int(r.scalar_one_or_none() or 0)


@pytest.mark.asyncio
async def test_receive_then_pick_then_count(session: AsyncSession):
    svc = StockService()
    item_id = 1
    wh = 1

    # 强护栏口径：非批次商品用 NULL 槽位
    batch_code: str | None = None

    # 1) 入库 +2（日期参数允许传入，但在无批次槽位下会被归一为 None）
    await svc.adjust(
        session=session,
        item_id=item_id,
        delta=2,
        reason=MovementType.INBOUND,
        ref="Q-IPC-1",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code=batch_code,
        production_date=date.today(),
        warehouse_id=wh,
    )
    q1 = await _qty(session, item_id, wh, batch_code)
    assert q1 >= 2

    # 2) 拣货 -1（无批次商品允许 batch_code=NULL）
    await svc.adjust(
        session=session,
        item_id=item_id,
        delta=-1,
        reason=MovementType.OUTBOUND,
        ref="Q-IPC-2",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code=batch_code,
        warehouse_id=wh,
    )
    q2 = await _qty(session, item_id, wh, batch_code)
    assert q2 == q1 - 1

    # 3) 盘点：把数量调整为 1（delta = 1 - 当前）
    remain = await _qty(session, item_id, wh, batch_code)
    delta = 1 - remain
    if delta != 0:
        await svc.adjust(
            session=session,
            item_id=item_id,
            delta=delta,
            reason=MovementType.COUNT,
            ref="Q-IPC-3",
            ref_line=1,
            occurred_at=datetime.now(UTC),
            batch_code=batch_code,
            production_date=date.today(),
            warehouse_id=wh,
        )
    q3 = await _qty(session, item_id, wh, batch_code)
    assert q3 == 1
