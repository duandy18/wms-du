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
async def test_new_platforms_minimal_end2end():
    """
    验证 tmall / douyin / xhs 三个平台的事件在桥接层能稳定进入业务入口：
      - 事件自带 lines → 进入扣减
      - 扣减后 stocks 数量正确
      - 幂等：重复执行不再扣减
    """
    eng = create_async_engine(ASYNC_URL, future=True)
    Session = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)

    async with Session() as s:
        # 维度 & 基线
        await s.execute(text("INSERT INTO warehouses (id, name) VALUES (1,'WH-1') ON CONFLICT (id) DO NOTHING"))
        await s.execute(text("""
            INSERT INTO items (id, sku, name, unit)
            VALUES (101, 'SKU-TM-101', 'TM-ITEM', 'PCS'),
                   (201, 'SKU-DY-201', 'DY-ITEM', 'PCS'),
                   (301, 'SKU-XHS-301','XHS-ITEM','PCS')
            ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, unit=EXCLUDED.unit
        """))
        await s.execute(text("""
            INSERT INTO locations (id, warehouse_id, name)
            VALUES (11, 1, 'L-11'), (12, 1, 'L-12'), (13, 1, 'L-13')
            ON CONFLICT (id) DO NOTHING
        """))
        await s.execute(text("""
            INSERT INTO stocks (item_id, location_id, qty) VALUES
                (101, 11, 10),
                (201, 12, 20),
                (301, 13, 30)
            ON CONFLICT (item_id, location_id) DO UPDATE SET qty=EXCLUDED.qty
        """))
        # 清理这组 ref 的既有账
        await s.execute(text("DELETE FROM stock_ledger WHERE ref IN ('TM-REF-1','DY-REF-1','XHS-REF-1')"))
        await s.execute(text("DELETE FROM outbound_commits WHERE ref IN ('TM-REF-1','DY-REF-1','XHS-REF-1')"))
        await s.commit()

        # 三个平台各一条
        events = [
            # tmall
            {
                "platform": "tmall",
                "tid": "TM-REF-1",
                "trade_status": "WAIT_SELLER_SEND_GOODS",
                "shop_id": "TM-SHOP-1",
                "lines": [{"item_id": 101, "location_id": 11, "qty": 3}],
            },
            # douyin
            {
                "platform": "douyin",
                "order_id": "DY-REF-1",
                "status": "PAID",
                "shop_id": "DY-SHOP-9",
                "lines": [{"item_id": 201, "location_id": 12, "qty": 5}],
            },
            # xhs
            {
                "platform": "xhs",
                "order_id": "XHS-REF-1",
                "status": "PAID",
                "shop_id": "XHS-SHOP-7",
                "lines": [{"item_id": 301, "location_id": 13, "qty": 7}],
            },
        ]
        await handle_event_batch(events, session=s)
        await s.commit()

        # 校验扣减
        rows = (await s.execute(text("""
            SELECT item_id, qty FROM stocks WHERE (item_id,location_id) IN ((101,11),(201,12),(301,13))
        """))).all()
        qty = {r[0]: r[1] for r in rows}
        assert qty[101] == 7   # 10 - 3
        assert qty[201] == 15  # 20 - 5
        assert qty[301] == 23  # 30 - 7

        # 幂等：再执行同一批 → 不变
        await handle_event_batch(events, session=s)
        await s.commit()
        rows2 = (await s.execute(text("""
            SELECT item_id, qty FROM stocks WHERE (item_id,location_id) IN ((101,11),(201,12),(301,13))
        """))).all()
        qty2 = {r[0]: r[1] for r in rows2}
        assert qty2[101] == 7
        assert qty2[201] == 15
        assert qty2[301] == 23
