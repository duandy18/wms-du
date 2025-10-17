import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.outbound_service import commit_outbound

pytestmark = pytest.mark.asyncio


async def _seed_stock(session: AsyncSession, item_id: int, location_id: int, qty: int):
    await session.execute(
        text(
            """
        INSERT INTO stocks(item_id, location_id, qty)
        VALUES (:i, :l, :q)
        ON CONFLICT (item_id, location_id) DO UPDATE SET qty=:q
    """
        ),
        dict(i=item_id, l=location_id, q=qty),
    )


async def _get_qty(session: AsyncSession, item_id: int, location_id: int) -> int:
    row = (
        await session.execute(
            text("SELECT qty FROM stocks WHERE item_id=:i AND location_id=:l"),
            dict(i=item_id, l=location_id),
        )
    ).first()
    return 0 if row is None else int(row.qty)


async def _ledger_count(session: AsyncSession, reason: str, ref: str) -> int:
    row = (
        await session.execute(
            text("SELECT COUNT(*) AS c FROM stock_ledger WHERE reason=:r AND ref=:ref"),
            dict(r=reason, ref=ref),
        )
    ).first()
    return int(row.c)


async def test_outbound_idempotency(session: AsyncSession):
    item_id, loc_id, ref = 1, 1, "SO-OUT-1"

    # 外层 fixture 已开事务，这里用嵌套事务（SAVEPOINT）
    async with session.begin_nested():
        await _seed_stock(session, item_id, loc_id, 10)

    async with session.begin_nested():
        res = await commit_outbound(
            session, ref, [{"item_id": item_id, "location_id": loc_id, "qty": 3}]
        )
        assert res[0]["status"] == "OK" and res[0]["committed_qty"] == 3

    async with session.begin_nested():
        res2 = await commit_outbound(
            session, ref, [{"item_id": item_id, "location_id": loc_id, "qty": 3}]
        )
        assert res2[0]["status"] == "IDEMPOTENT" and res2[0]["committed_qty"] == 0

    assert await _get_qty(session, item_id, loc_id) == 7
    assert await _ledger_count(session, "OUTBOUND", ref) == 1


async def test_outbound_insufficient_stock(session: AsyncSession):
    item_id, loc_id, ref = 2, 1, "SO-OUT-2"

    async with session.begin_nested():
        await _seed_stock(session, item_id, loc_id, 5)

    async with session.begin_nested():
        res = await commit_outbound(
            session, ref, [{"item_id": item_id, "location_id": loc_id, "qty": 9}]
        )
        assert res[0]["status"] == "INSUFFICIENT_STOCK"
        assert res[0]["committed_qty"] == 0

    assert await _get_qty(session, item_id, loc_id) == 5
    assert await _ledger_count(session, "OUTBOUND", ref) == 0
