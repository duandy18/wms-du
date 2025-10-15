# tests/quick/test_inbound_idempotent_pg.py
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.location import Location
from app.models.stock import Stock
from app.services.inbound_service import InboundService
from app.services.stock_service import StockService

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def svc() -> InboundService:
    return InboundService(StockService())


async def _ensure_item(session: AsyncSession, sku: str = "SKU-1001") -> int:
    item_id = await session.scalar(select(Item.id).where(Item.sku == sku))
    if item_id:
        return int(item_id)
    await session.execute(
        text("INSERT INTO items (sku, name) VALUES (:s, :n)"), {"s": sku, "n": sku}
    )
    item_id = await session.scalar(select(Item.id).where(Item.sku == sku))
    return int(item_id)


async def _ensure_location(session: AsyncSession) -> int:
    # 你的 Location 模型无 code 列；直接复用/插入 id=1 的最小库位
    loc_id = await session.scalar(select(Location.id).order_by(Location.id.asc()).limit(1))
    if loc_id is not None:
        return int(loc_id)
    await session.execute(
        text(
            "INSERT INTO locations (id, name, warehouse_id) VALUES (1, 'LOC-TEST', 1) ON CONFLICT (id) DO NOTHING"
        )
    )
    return 1


async def _stock_qty(session: AsyncSession, item_id: int, location_id: int) -> int:
    row = await session.scalar(
        select(Stock).where(Stock.item_id == item_id, Stock.location_id == location_id).limit(1)
    )
    return int(getattr(row, "qty", 0) if row else 0)


async def test_inbound_receive_idempotent(session: AsyncSession, svc: InboundService):
    sku = "SKU-1001"
    item_id = await _ensure_item(session, sku)
    loc_id = await _ensure_location(session)

    # 第一次收货 —— 直接调用 + 提交
    r1 = await svc.receive(
        session=session,
        sku=sku,
        qty=10,
        ref="PO-1",
        ref_line=1,
        occurred_at=datetime.now(UTC),
    )
    await session.commit()

    q1 = await _stock_qty(session, item_id=item_id, location_id=loc_id)
    assert q1 == 10
    assert r1["idempotent"] is False

    # 第二次同键回放 —— 仍然直接调用 + 提交（不应再加库存）
    r2 = await svc.receive(
        session=session,
        sku=sku,
        qty=10,
        ref="PO-1",
        ref_line=1,
        occurred_at=datetime.now(UTC),
    )
    await session.commit()

    q2 = await _stock_qty(session, item_id=item_id, location_id=loc_id)
    assert q2 == 10
    assert r2["idempotent"] is True
