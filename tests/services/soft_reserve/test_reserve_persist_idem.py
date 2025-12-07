import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.soft_reserve_service import SoftReserveService

PLATFORM = "pdd"
SHOP_ID = "1"
WH_ID = 1
ITEM = 3003


@pytest.mark.asyncio
async def test_reserve_persist_idempotent(
    db_session_like_pg: AsyncSession,
    _maker: async_sessionmaker[AsyncSession],  # ← 从 conftest 提供的工厂拿独立会话
):
    ref = "RSV-3003-7"

    # 清理
    await db_session_like_pg.execute(
        text(
            "DELETE FROM reservation_lines USING reservations r WHERE reservation_id=r.id AND r.ref=:r"
        ),
        {"r": ref},
    )
    await db_session_like_pg.execute(text("DELETE FROM reservations WHERE ref=:r"), {"r": ref})
    await db_session_like_pg.commit()

    svc = SoftReserveService()
    lines = [{"item_id": ITEM, "qty": 7}]

    # 并发 32 次，每个任务独立会话；用信号量控制瞬时并发，保护连接池
    sem = asyncio.Semaphore(12)

    async def _fire_one():
        async with sem:
            async with _maker() as s:
                return await svc.persist(
                    s,
                    platform=PLATFORM,
                    shop_id=SHOP_ID,
                    warehouse_id=WH_ID,
                    ref=ref,
                    lines=lines,
                )

    results = await asyncio.gather(*(_fire_one() for _ in range(32)))
    ids = {res["reservation_id"] for res in results}
    assert len(ids) == 1, f"reservation ids not deduped: {ids}"

    # reservations 只有 1 条
    r = await db_session_like_pg.execute(
        text(
            "SELECT COUNT(*) FROM reservations "
            "WHERE platform=:p AND shop_id=:s AND warehouse_id=:w AND ref=:r"
        ),
        {"p": PLATFORM, "s": SHOP_ID, "w": WH_ID, "r": ref},
    )
    assert int(r.scalar() or 0) == 1
