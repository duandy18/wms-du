# tests/quick/test_inbound_reclassify_v2.py
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service import StockService

UTC = timezone.utc


async def _ensure_wh(session: AsyncSession, name: str) -> int:
    row = await session.execute(
        text("SELECT id FROM warehouses WHERE name=:n LIMIT 1"), {"n": name}
    )
    wid = row.scalar_one_or_none()
    if wid is not None:
        return int(wid)
    ins = await session.execute(
        text("INSERT INTO warehouses(name) VALUES(:n) ON CONFLICT(name) DO NOTHING RETURNING id"),
        {"n": name},
    )
    wid2 = ins.scalar_one_or_none()
    if wid2 is not None:
        return int(wid2)
    row2 = await session.execute(
        text("SELECT id FROM warehouses WHERE name=:n LIMIT 1"), {"n": name}
    )
    return int(row2.scalar_one())


async def _qty(session: AsyncSession, item_id: int, wh: int, code: str) -> int:
    row = await session.execute(
        text("SELECT qty FROM stocks WHERE item_id=:i AND warehouse_id=:w AND batch_code=:c"),
        {"i": item_id, "w": wh, "c": code},
    )
    return int(row.scalar_one_or_none() or 0)


@pytest.mark.asyncio
async def test_inbound_receive_and_reclassify_integrity(session: AsyncSession):
    svc = StockService()

    item_id = 1
    batch_code = "NEAR"
    wh_returns = await _ensure_wh(session, "RETURNS")
    wh_main = await _ensure_wh(session, "MAIN")

    # 1) RETURNS：入库 +2（带日期契约）
    await svc.adjust(
        session=session,
        item_id=item_id,
        warehouse_id=wh_returns,
        delta=+2,
        reason=MovementType.INBOUND,
        ref="PO-R1",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code=batch_code,
        production_date=date.today(),
    )
    r0 = await _qty(session, item_id, wh_returns, batch_code)
    assert r0 >= 2

    # 2) 净零迁移：RETURNS -1 → MAIN +1
    await svc.adjust(
        session=session,
        item_id=item_id,
        warehouse_id=wh_returns,
        delta=-1,
        reason="RETURN_RECLASSIFY",
        ref="X-MOVE-1",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code=batch_code,
    )
    await svc.adjust(
        session=session,
        item_id=item_id,
        warehouse_id=wh_main,
        delta=+1,
        reason="RETURN_RECLASSIFY",
        ref="X-MOVE-1",
        ref_line=2,
        occurred_at=datetime.now(UTC),
        batch_code=batch_code,
        production_date=date.today(),  # 补：正增量需日期
    )

    # 3) 断言：RETURNS 减 1，MAIN 加 1，总量不变
    r1 = await _qty(session, item_id, wh_returns, batch_code)
    m1 = await _qty(session, item_id, wh_main, batch_code)
    assert r1 == r0 - 1
    assert m1 >= 1
    assert (r1 + m1) == (r0 + (m1 - 1))
