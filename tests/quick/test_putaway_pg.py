# tests/quick/test_putaway_pg.py
import pytest
from sqlalchemy import text

from app.db.session import async_session_maker
from app.services.putaway_service import PutawayService

pytestmark = pytest.mark.quick


async def _ensure_item_and_locs(*, item_id=1, stage_loc=10, target_loc=101):
    """最小造数：仓、品、库位（id 显式，避免 sequence 依赖）"""
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
                    VALUES (:l, :n, 1)
                    ON CONFLICT (id) DO NOTHING
                """
                ),
                {"l": lid, "n": name},
            )


async def _set_stock(item_id: int, location_id: int, qty: int):
    async with async_session_maker() as s, s.begin():
        await s.execute(
            text(
                """
                INSERT INTO stocks (item_id, location_id, qty)
                VALUES (:i, :l, :q)
                ON CONFLICT (item_id, location_id)
                DO UPDATE SET qty = EXCLUDED.qty
            """
            ),
            {"i": item_id, "l": location_id, "q": qty},
        )


async def _get_qty(item_id: int, location_id: int) -> int:
    async with async_session_maker() as s:
        return int(
            (
                await s.execute(
                    text("SELECT qty FROM stocks WHERE item_id=:i AND location_id=:l"),
                    {"i": item_id, "l": location_id},
                )
            ).scalar()
            or 0
        )


async def _sum_putaway_ledger(item_id: int) -> tuple[int, int, int]:
    """
    返回 (行数, neg_sum, pos_sum)，只统计 PUTAWAY 且关联到该 item 的 stock。
    """
    async with async_session_maker() as s:
        rows = (
            await s.execute(
                text(
                    """
            SELECT sl.delta
            FROM stock_ledger sl
            JOIN stocks st ON st.id = sl.stock_id
            WHERE sl.reason='PUTAWAY' AND st.item_id=:i
        """
                ),
                {"i": item_id},
            )
        ).all()
        deltas = [int(r[0]) for r in rows]
        return (
            len(deltas),
            sum(x for x in deltas if x < 0),
            sum(x for x in deltas if x > 0),
        )


@pytest.mark.asyncio
async def test_putaway_integrity():
    item_id, stage, target = 1, 10, 101

    # 造基础数据：仓/品/库位，并把 STAGE 设为 10
    await _ensure_item_and_locs(item_id=item_id, stage_loc=stage, target_loc=target)
    await _set_stock(item_id=item_id, location_id=stage, qty=10)
    await _set_stock(item_id=item_id, location_id=target, qty=0)

    # 跑一次 putaway，把 10 从 STAGE → 目标库位
    def locator(_item: int) -> int:
        return target

    async with async_session_maker() as session:
        res = await PutawayService.bulk_putaway(
            session,
            stage_location_id=stage,
            target_locator_fn=locator,
            batch_size=100,
            worker_id="QK",
        )
        # bulk_putaway 内部会 commit
        assert res["moved"] >= 1

    # 校验库存
    q_stage = await _get_qty(item_id, stage)
    q_target = await _get_qty(item_id, target)

    # 校验台账：两条 PUTAWAY（出/入）且数值守恒 -10 / +10
    rows, neg_sum, pos_sum = await _sum_putaway_ledger(item_id)
    print(f"putaway ledger: {rows} {q_stage} {neg_sum} {pos_sum}")
    print(f"stocks: {q_stage} {q_target}")

    assert q_stage == 0
    assert q_target == 10
    assert rows == 2
    assert neg_sum == -10 and pos_sum == 10
