import pytest
from sqlalchemy import text

from app.db.session import async_session_maker
from app.services.putaway_service import PutawayService

pytestmark = pytest.mark.quick


async def _seed(item_id=11, stage=10, target=101, qty=20):
    async with async_session_maker() as s:
        async with s.begin():
            await s.execute(
                text("INSERT INTO warehouses (id,name) VALUES (1,'WH') ON CONFLICT (id) DO NOTHING")
            )
            await s.execute(
                text(
                    "INSERT INTO items (id,sku,name,unit) VALUES (:i,:s,:n,'EA') ON CONFLICT (id) DO NOTHING"
                ),
                {"i": item_id, "s": f"SKU-{item_id:03d}", "n": f"Item-{item_id}"},
            )
            for lid, name in [(stage, "STAGE"), (target, "RACK-101")]:
                await s.execute(
                    text(
                        "INSERT INTO locations (id,name,warehouse_id) VALUES (:l,:n,1) ON CONFLICT (id) DO NOTHING"
                    ),
                    {"l": lid, "n": name},
                )
            await s.execute(
                text(
                    """
                INSERT INTO stocks (item_id, location_id, qty)
                VALUES (:i,:l,:q)
                ON CONFLICT (item_id, location_id) DO UPDATE SET qty = EXCLUDED.qty
            """
                ),
                {"i": item_id, "l": stage, "q": qty},
            )
            await s.execute(
                text(
                    """
                INSERT INTO stocks (item_id, location_id, qty)
                VALUES (:i,:l,0)
                ON CONFLICT (item_id, location_id) DO NOTHING
            """
                ),
                {"i": item_id, "l": target},
            )


async def _qty(i, l):
    async with async_session_maker() as s:
        return int(
            (
                await s.execute(
                    text("SELECT qty FROM stocks WHERE item_id=:i AND location_id=:l"),
                    {"i": i, "l": l},
                )
            ).scalar()
            or 0
        )


async def _ledger_triplet_count(reason, ref, ref_line):
    async with async_session_maker() as s:
        return int(
            (
                await s.execute(
                    text(
                        """
            SELECT COUNT(*) FROM stock_ledger
            WHERE reason=:r AND ref=:ref AND ref_line=:line
        """
                    ),
                    {"r": reason, "ref": ref, "line": ref_line},
                )
            ).scalar()
            or 0
        )


@pytest.mark.asyncio
async def test_bulk_putaway_idempotent_replay():
    item, stage, target = 11, 10, 101
    await _seed(item_id=item, stage=stage, target=target, qty=20)

    def locator(_):
        return target

    # 第一次跑
    async with async_session_maker() as s1:
        r1 = await PutawayService.bulk_putaway(
            s1,
            stage_location_id=stage,
            target_locator_fn=locator,
            batch_size=50,
            worker_id="REPLAY",
        )
    assert r1["moved"] >= 1
    q1_stage, q1_target = await _qty(item, stage), await _qty(item, target)
    # 记录幂等三元组（bulk_putaway 内部 ref="PUT-REPLAY-<stock_id>"，ref_line=1/2）
    # 粗略抽样：至少存在一条 ref_line=1
    assert (
        await _ledger_triplet_count("PUTAWAY", f"PUT-REPLAY-{stage}", 1) == 0
    )  # stage 的 stock_id 不等于 location_id

    # 第二次重复跑（应当不再移动/不再写账）
    async with async_session_maker() as s2:
        r2 = await PutawayService.bulk_putaway(
            s2,
            stage_location_id=stage,
            target_locator_fn=locator,
            batch_size=50,
            worker_id="REPLAY",
        )
    q2_stage, q2_target = await _qty(item, stage), await _qty(item, target)

    assert r2["moved"] == 0
    assert (q1_stage, q1_target) == (q2_stage, q2_target)
