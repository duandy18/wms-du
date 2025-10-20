import os
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from app.services.platform_events import handle_event_batch

ASYNC_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms"
).replace("postgresql+psycopg", "postgresql+asyncpg")


@pytest.mark.asyncio
async def test_same_platform_multi_shops_isolated_idempotency():
    """
    同一平台（pdd），两个不同 shop_id，用“同一个 ref”并行：
      - A 店扣减后 qtyA 正确，B 店扣减后 qtyB 正确，互不影响
      - 重放同店幂等，不再扣减
    """
    eng = create_async_engine(ASYNC_URL, future=True)
    Session = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)

    async with Session() as s:
        # 维度 & 基线
        await s.execute(text("INSERT INTO warehouses (id, name) VALUES (1,'WH-1') ON CONFLICT (id) DO NOTHING"))
        await s.execute(text("""
            INSERT INTO items (id, sku, name, unit)
            VALUES (501, 'SKU-PDD-501', 'PDD-ITEM', 'PCS')
            ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, unit=EXCLUDED.unit
        """))
        await s.execute(text("""
            INSERT INTO locations (id, warehouse_id, name)
            VALUES (51, 1, 'L-51'), (52, 1, 'L-52')
            ON CONFLICT (id) DO NOTHING
        """))
        await s.execute(text("""
            INSERT INTO stocks (item_id, location_id, qty) VALUES
                (501, 51, 10),
                (501, 52, 10)
            ON CONFLICT (item_id, location_id) DO UPDATE SET qty=EXCLUDED.qty
        """))
        await s.execute(text("DELETE FROM stock_ledger WHERE ref LIKE 'MS-REF-%'"))
        await s.execute(text("DELETE FROM outbound_commits WHERE ref LIKE 'MS-REF-%'"))
        await s.commit()

        # 同平台 pdd，同 ref，不同店 A/B，各扣 3
        ref = "MS-REF-001"
        events = [
            {
                "platform": "pdd",
                "order_sn": ref,
                "status": "PAID",
                "shop_id": "SHOP-A",
                "lines": [{"item_id": 501, "location_id": 51, "qty": 3}],
            },
            {
                "platform": "pdd",
                "order_sn": ref,
                "status": "PAID",
                "shop_id": "SHOP-B",
                "lines": [{"item_id": 501, "location_id": 52, "qty": 3}],
            },
        ]
        await handle_event_batch(events, session=s)
        await s.commit()

        # 校验：两条库存各自扣减
        qty_a = (await s.execute(text("SELECT qty FROM stocks WHERE item_id=501 AND location_id=51"))).scalar_one()
        qty_b = (await s.execute(text("SELECT qty FROM stocks WHERE item_id=501 AND location_id=52"))).scalar_one()
        assert qty_a == 7 and qty_b == 7

        # 同店重放 → 幂等
        await handle_event_batch(events, session=s)
        await s.commit()

        qty_a2 = (await s.execute(text("SELECT qty FROM stocks WHERE item_id=501 AND location_id=51"))).scalar_one()
        qty_b2 = (await s.execute(text("SELECT qty FROM stocks WHERE item_id=501 AND location_id=52"))).scalar_one()
        assert qty_a2 == 7 and qty_b2 == 7
