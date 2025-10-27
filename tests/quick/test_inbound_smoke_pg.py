import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

async def _ensure_min_domain(session: AsyncSession, item_id: int = 777, loc_id: int = 1) -> int:
    await session.execute(text("INSERT INTO warehouses(id,name) VALUES (1,'WH-1') ON CONFLICT (id) DO NOTHING"))
    await session.execute(text("INSERT INTO locations(id,name,warehouse_id) VALUES (:l,'L1',1) ON CONFLICT (id) DO NOTHING"), {"l": loc_id})
    await session.execute(
        text("INSERT INTO items(id,sku,name,unit) VALUES (:i,:s,:n,'bag') ON CONFLICT (id) DO NOTHING"),
        {"i": item_id, "s": f"SKU-{item_id}", "n": f"ITEM-{item_id}"}
    )
    await session.execute(
        text("INSERT INTO stocks(item_id,location_id,qty) VALUES (:i,:l,0) ON CONFLICT (item_id,location_id) DO NOTHING"),
        {"i": item_id, "l": loc_id}
    )
    await session.commit()
    sid = (await session.execute(
        text("SELECT id FROM stocks WHERE item_id=:i AND location_id=:l"), {"i": item_id, "l": loc_id}
    )).scalar_one()
    return int(sid)

async def test_inbound_putaway_ledger_snapshot_smoke(session: AsyncSession):
    ITEM, LOC = 777, 1
    stock_id = await _ensure_min_domain(session, ITEM, LOC)

    before = (await session.execute(text("SELECT qty FROM stocks WHERE id=:sid"), {"sid": stock_id})).scalar_one() or 0
    after = int(before) + 5

    # 模拟“入库+上架”合并 +5，并写台账
    await session.execute(text("UPDATE stocks SET qty=:q WHERE id=:sid"), {"q": after, "sid": stock_id})
    await session.execute(text("""
        INSERT INTO stock_ledger (stock_id,item_id,delta,after_qty,occurred_at,reason,ref,ref_line)
        VALUES (:sid,:item,5,:after, NOW(), 'INBOUND','SMOKE-INBOUND',1)
    """), {"sid": stock_id, "item": ITEM, "after": after})
    await session.commit()

    # ✅ 断言 stocks 与台账
    qty_now = (await session.execute(text("SELECT qty FROM stocks WHERE id=:sid"), {"sid": stock_id})).scalar_one()
    assert int(qty_now) == after

    row = (await session.execute(text("""
        SELECT reason, delta, after_qty FROM stock_ledger
        WHERE item_id=:item ORDER BY id DESC LIMIT 1
    """), {"item": ITEM})).first()
    assert row is not None and row.reason == "INBOUND" and int(row.delta) == 5 and int(row.after_qty) == after
