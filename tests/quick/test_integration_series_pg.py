# tests/quick/test_integration_series_pg.py
import pytest
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.services.inbound_service import InboundService
from app.services.stock_service import StockService
from app.services.putaway_service import PutawayService
from app.models.item import Item
from app.models.location import Location
from app.models.stock import Stock

pytestmark = pytest.mark.asyncio


async def _ensure_item(session: AsyncSession, sku: str = "SKU-3001") -> int:
    iid = await session.scalar(select(Item.id).where(Item.sku == sku))
    if iid:
        return int(iid)
    await session.execute(
        text("INSERT INTO items (sku, name) VALUES (:s, :n)"),
        {"s": sku, "n": sku},
    )
    # 不强制 commit，复用同一事务读取
    return int(await session.scalar(select(Item.id).where(Item.sku == sku)))


async def _ensure_location(session: AsyncSession, name: str, loc_id: int) -> int:
    """与当前 schema 对齐：locations(id, name, warehouse_id)，不再使用 code 列。"""
    exist = await session.scalar(select(Location.id).where(Location.id == loc_id))
    if exist is None:
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


async def test_receive_then_putaway_and_replay(session: AsyncSession):
    sku = "SKU-3001"
    item_id = await _ensure_item(session, sku)
    stage = await _ensure_location(session, "STAGE", 0)
    rack = await _ensure_location(session, "RACK-B1", 201)

    # 收货 10 到 STAGE（避免与外层/fixture 的事务冲突：不再使用 session.begin）
    svc = InboundService(StockService())
    res1 = await svc.receive(
        session=session,
        sku=sku,
        qty=10,
        ref="PO-3001",
        ref_line=1,
        occurred_at=datetime.now(timezone.utc),
    )
    await session.commit()
    assert res1["idempotent"] is False
    assert await _stock_qty(session, item_id, stage) == 10

    # Putaway 6 到 RACK-B1
    res2 = await PutawayService.putaway(
        session=session,
        item_id=item_id,
        from_location_id=stage,
        to_location_id=rack,
        qty=6,
        ref="PUT-3001",
        ref_line=1,
    )
    await session.commit()
    assert res2["status"] in ("ok", "idempotent")
    assert (await _stock_qty(session, item_id, stage), await _stock_qty(session, item_id, rack)) == (4, 6)

    # 重放收货（应幂等）
    res3 = await svc.receive(
        session=session,
        sku=sku,
        qty=10,
        ref="PO-3001",
        ref_line=1,
        occurred_at=datetime.now(timezone.utc),
    )
    await session.commit()
    assert res3["idempotent"] is True
    assert (await _stock_qty(session, item_id, stage), await _stock_qty(session, item_id, rack)) == (4, 6)
