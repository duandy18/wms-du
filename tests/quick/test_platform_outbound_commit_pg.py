# tests/quick/test_platform_outbound_commit_pg.py
import os
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from app.services.platform_events import handle_event_batch

@pytest.mark.asyncio
async def test_paid_event_triggers_outbound_and_idempotent():
    """
    1) 造最小维度与库存：warehouses / items(sku,unit 必填) / locations / stocks
    2) 发送 PDD 的 PAID 事件（含 lines）
    3) 验证扣减与记账
    4) 重放事件 → 幂等
    """
    url = os.getenv("DATABASE_URL", "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms").replace(
        "postgresql+psycopg", "postgresql+asyncpg"
    )
    eng = create_async_engine(url, future=True)
    Session = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)

    async with Session() as s:
        # 1) 维度表（items 需提供 sku 与 unit）
        await s.execute(text("INSERT INTO warehouses (id, name) VALUES (1,'WH-1') ON CONFLICT (id) DO NOTHING"))
        await s.execute(text("""
            INSERT INTO items (id, sku, name, unit)
            VALUES (1, 'SKU-ITEM-1', 'ITEM-1', 'PCS')
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, unit = EXCLUDED.unit
        """))
        await s.execute(text("""
            INSERT INTO locations (id, warehouse_id, name)
            VALUES (1, 1, 'L-1')
            ON CONFLICT (id) DO NOTHING
        """))

        # 2) 确保有 stocks 行且 qty=10
        await s.execute(text("""
            INSERT INTO stocks (item_id, location_id, qty)
            VALUES (1, 1, 10)
            ON CONFLICT (item_id, location_id) DO UPDATE SET qty = EXCLUDED.qty
        """))
        await s.commit()

        # 3) 发送 PAID 事件（带 lines）
        ref = "P-PAID-001"
        events = [{
            "platform": "pdd",
            "order_sn": ref,
            "status": "PAID",
            "lines": [{"item_id": 1, "location_id": 1, "qty": 3}],
        }]
        await handle_event_batch(events, session=s)
        await s.commit()

        # 验证扣减与记账
        qty_after = (await s.execute(text(
            "SELECT qty FROM stocks WHERE item_id=1 AND location_id=1"
        ))).scalar_one()
        assert qty_after == 7  # 10 - 3

        ledger_count = (await s.execute(text(
            "SELECT COUNT(1) FROM stock_ledger WHERE reason='OUTBOUND' AND ref=:r"
        ), {"r": ref})).scalar_one()
        assert ledger_count == 1

        # 4) 重放事件 → 幂等（不再扣减、不再新增记账）
        await handle_event_batch(events, session=s)
        await s.commit()

        qty_again = (await s.execute(text(
            "SELECT qty FROM stocks WHERE item_id=1 AND location_id=1"
        ))).scalar_one()
        assert qty_again == 7

        ledger_count_again = (await s.execute(text(
            "SELECT COUNT(1) FROM stock_ledger WHERE reason='OUTBOUND' AND ref=:r"
        ), {"r": ref})).scalar_one()
        assert ledger_count_again == 1
