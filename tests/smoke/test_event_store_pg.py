# tests/smoke/test_event_store_pg.py
"""
Smoke test: verify outbound event writes to event_store (Phase 2.8)

要点：
1) 先幂等种子最小数据（warehouse/location/item/stock），避免业务流因数据缺失而短路；
2) 使用随机 ref，避免 (topic,key) 唯一约束撞车；
3) SQLAlchemy 2.x 裸 SQL 必须用 text() 包裹；
"""

import asyncio
import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.services.outbound_service import OutboundService

DATABASE_URL = "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms"


async def _seed_minimal(session):
    """幂等补齐仓库→库位→商品→库存"""
    sql = text(
        """
        -- 1) 仓库
        INSERT INTO warehouses(id, name) VALUES (1, 'WH-1')
        ON CONFLICT (id) DO NOTHING;

        -- 2) 库位
        INSERT INTO locations(id, warehouse_id, name)
        VALUES (1, 1, 'LOC-A')
        ON CONFLICT (id) DO UPDATE
          SET warehouse_id=EXCLUDED.warehouse_id, name=EXCLUDED.name;

        -- 3) 商品（items.sku NOT NULL；unit 非空，默认 PCS）
        INSERT INTO items(id, sku, name, unit)
        VALUES (1, 'SKU-TEST-1', 'TEST-ITEM', 'PCS')
        ON CONFLICT (id) DO UPDATE
          SET sku=EXCLUDED.sku, name=EXCLUDED.name, unit=EXCLUDED.unit;

        -- 4) 库存（(item_id,location_id) 唯一）
        INSERT INTO stocks(item_id, location_id, qty)
        VALUES (1, 1, 10)
        ON CONFLICT (item_id, location_id) DO UPDATE
          SET qty=EXCLUDED.qty;
        """
    )
    await session.execute(sql)
    await session.commit()


async def _apply_and_query():
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        # Step 0: 保证最小数据存在
        await _seed_minimal(session)

        # Step 1: 构造一笔最小可用事件；随机 ref 防止 (topic,key) 唯一键冲突
        ref = f"REF-{uuid.uuid4().hex[:8].upper()}"
        task = {
            "platform": "pdd",
            "shop_id": "S1",
            "ref": ref,
            "state": "PAID",
            "lines": [{"item_id": 1, "location_id": 1, "qty": 1}],
        }

        # 执行业务：应在提交点写入 event_store(topic='outbound.commit', key='S1:<ref>')
        await OutboundService.apply_event(task, session)

        # Step 2: 查询 event_store 最近写入
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id, topic, key, status, attempts, trace_id, last_error
                    FROM event_store
                    WHERE topic='outbound.commit'
                    ORDER BY id DESC
                    LIMIT 20
                    """
                )
            )
        ).mappings().all()

        print("\n== event_store recent rows ==")
        for r in rows:
            print(dict(r))

        key_expected = f"S1:{ref}"
        assert any(
            (r["topic"] == "outbound.commit") and (r["key"] == key_expected) for r in rows
        ), f"no outbound.commit event written for key={key_expected}"

    await engine.dispose()


def test_event_store_write():
    """确认事件被写入 event_store"""
    asyncio.run(_apply_and_query())
