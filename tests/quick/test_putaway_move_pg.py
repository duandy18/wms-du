# tests/quick/test_putaway_move_pg.py
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.location import Location
from app.models.stock import Stock
from app.services.putaway_service import PutawayService

pytestmark = pytest.mark.asyncio


async def _ensure_item(session: AsyncSession, sku="SKU-2001") -> int:
    iid = await session.scalar(select(Item.id).where(Item.sku == sku))
    if iid:
        return int(iid)
    await session.execute(
        text("INSERT INTO items (sku, name) VALUES (:s, :n)"), {"s": sku, "n": sku}
    )
    return int(await session.scalar(select(Item.id).where(Item.sku == sku)))


async def _ensure_location(session: AsyncSession, loc_id: int, name: str) -> int:
    """
    你的 locations 表没有 code 列，这里仅使用 (id, name, warehouse_id) 三列最小化插入。
    """
    exists = await session.scalar(select(Location.id).where(Location.id == loc_id))
    if exists is None:
        await session.execute(
            text(
                "INSERT INTO locations (id, name, warehouse_id) "
                "VALUES (:i, :n, 1) ON CONFLICT (id) DO NOTHING"
            ),
            {"i": loc_id, "n": name},
        )
    return loc_id


async def _stock_qty(session: AsyncSession, item_id: int, location_id: int) -> int:
    row = await session.scalar(
        select(Stock).where(Stock.item_id == item_id, Stock.location_id == location_id)
    )
    return int(getattr(row, "qty", 0) if row else 0)


async def test_putaway_out_in_pair(session: AsyncSession):
    # 造基础数据
    sku = "SKU-2001"
    item_id = await _ensure_item(session, sku)
    stage = await _ensure_location(session, 0, "STAGE")
    rack = await _ensure_location(session, 101, "RACK-A1")

    # 在 STAGE 造 10 个库存（注意：stocks 无 updated_at 列）
    await session.execute(
        text(
            "INSERT INTO stocks (item_id, location_id, qty) "
            "VALUES (:i,:l,:q) "
            "ON CONFLICT (item_id,location_id) DO UPDATE SET qty=EXCLUDED.qty"
        ),
        {"i": item_id, "l": stage, "q": 10},
    )
    await session.commit()

    # 移 7 个到 RACK-A1
    res = await PutawayService.putaway(
        session=session,
        item_id=item_id,
        from_location_id=stage,
        to_location_id=rack,
        qty=7,
        ref="PUT-TEST-1",
        ref_line=1,
    )
    await session.commit()
    assert res["status"] in ("ok", "idempotent")

    q_stage = await _stock_qty(session, item_id, stage)
    q_rack = await _stock_qty(session, item_id, rack)
    assert (q_stage, q_rack) == (3, 7)

    # 再次重复 putaway（同 ref/ref_line），不应改变库存（命中幂等）
    res2 = await PutawayService.putaway(
        session=session,
        item_id=item_id,
        from_location_id=stage,
        to_location_id=rack,
        qty=7,
        ref="PUT-TEST-1",
        ref_line=1,
    )
    await session.commit()
    assert res2["status"] == "idempotent"

    q_stage2 = await _stock_qty(session, item_id, stage)
    q_rack2 = await _stock_qty(session, item_id, rack)
    assert (q_stage2, q_rack2) == (3, 7)
