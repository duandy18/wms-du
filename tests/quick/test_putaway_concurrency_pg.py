import asyncio

import pytest
from sqlalchemy import text

from app.db.session import async_session_maker
from app.services.putaway_service import PutawayService

pytestmark = pytest.mark.smoke


async def _seed_stage(item_id=2, stage_loc=10, target_loc=101, qty=40):
    async with async_session_maker() as s, s.begin():
        await s.execute(
            text("INSERT INTO warehouses (id, name) VALUES (1,'WH') ON CONFLICT (id) DO NOTHING")
        )
        await s.execute(
            text(
                """
                INSERT INTO items (id, sku, name, unit)
                VALUES (:i, :s, :n, 'EA')
                ON CONFLICT (id) DO NOTHING
            """
            ),
            {"i": item_id, "s": f"SKU-{item_id:03d}", "n": f"Item-{item_id}"},
        )
        for lid, name in [(stage_loc, "STAGE"), (target_loc, "RACK-101")]:
            await s.execute(
                text(
                    """
                    INSERT INTO locations (id, name, warehouse_id)
                    VALUES (:l,:n,1) ON CONFLICT (id) DO NOTHING
                """
                ),
                {"l": lid, "n": name},
            )
        # STAGE 汇总直接设定
        await s.execute(
            text(
                """
                INSERT INTO stocks (item_id, location_id, qty)
                VALUES (:i, :l, :q)
                ON CONFLICT (item_id, location_id) DO UPDATE SET qty = EXCLUDED.qty
            """
            ),
            {"i": item_id, "l": stage_loc, "q": qty},
        )


async def _qty(item, loc):
    async with async_session_maker() as s:
        return int(
            (
                await s.execute(
                    text("SELECT qty FROM stocks WHERE item_id=:i AND location_id=:l"),
                    {"i": item, "l": loc},
                )
            ).scalar()
            or 0
        )


@pytest.mark.asyncio
async def test_bulk_putaway_concurrency_skip_locked():
    item_id, stage, target = 2, 10, 101
    await _seed_stage(item_id=item_id, stage_loc=stage, target_loc=target, qty=40)

    def locator(_item):
        return target

    # 关键：并发时每个 worker 使用**独立**的 AsyncSession
    async with async_session_maker() as s1, async_session_maker() as s2:
        t1 = asyncio.create_task(
            PutawayService.bulk_putaway(
                s1,
                stage_location_id=stage,
                target_locator_fn=locator,
                batch_size=50,
                worker_id="A",
            )
        )
        t2 = asyncio.create_task(
            PutawayService.bulk_putaway(
                s2,
                stage_location_id=stage,
                target_locator_fn=locator,
                batch_size=50,
                worker_id="B",
            )
        )
        r1, r2 = await asyncio.gather(t1, t2)

    # 断言：STAGE 清空、目标满额；claimed/moved 有值
    assert await _qty(item_id, stage) == 0
    assert await _qty(item_id, target) == 40
    assert (r1["claimed"] + r2["claimed"]) >= 1
    assert (r1["moved"] + r2["moved"]) >= 1
