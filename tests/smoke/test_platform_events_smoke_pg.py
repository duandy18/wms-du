# tests/smoke/test_platform_events_smoke_pg.py
"""
多平台平台事件 → pipeline 冒烟测试（v2 schema 版）。
"""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.services.platform_events import handle_event_batch

ASYNC_URL = (
    os.getenv("WMS_TEST_DATABASE_URL")
    or os.getenv("WMS_DATABASE_URL")
    or "postgresql+asyncpg://postgres:wms@127.0.0.1:55432/postgres"
)


@pytest.mark.asyncio
async def test_smoke_multi_platform_end2end():
    eng = create_async_engine(ASYNC_URL, future=True)
    Session = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)

    async with Session() as s:
        # ---------- 1) 维度与初始库存 ----------
        await s.execute(
            text(
                "INSERT INTO warehouses (id, name) VALUES (1,'WH-1') ON CONFLICT (id) DO NOTHING"
            )
        )
        await s.execute(
            text(
                """
            INSERT INTO items (id, sku, name, uom)
            VALUES
              (1, 'SKU-1', 'ITEM-1', 'PCS'),
              (2, 'SKU-2', 'ITEM-2', 'PCS'),
              (3, 'SKU-3', 'ITEM-3', 'PCS')
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, uom = EXCLUDED.uom
        """
            )
        )
        await s.execute(
            text(
                """
            INSERT INTO locations (id, warehouse_id, name)
            VALUES (1, 1, 'L-1')
            ON CONFLICT (id) DO NOTHING
        """
            )
        )
        # v2 stocks：按 (warehouse_id, item_id, batch_code) 建唯一槽位
        await s.execute(
            text(
                """
            INSERT INTO stocks (warehouse_id, item_id, batch_code, qty) VALUES
              (1, 1, 'B-1', 10),
              (1, 2, 'B-2', 20),
              (1, 3, 'B-3',  5)
            ON CONFLICT ON CONSTRAINT uq_stocks_item_wh_batch
            DO UPDATE SET qty = EXCLUDED.qty
        """
            )
        )
        await s.commit()

        # ---------- 2) 多平台“已发货”事件 ----------
        ref_p, ref_t, ref_j = "P-SMOKE-001", "T-SMOKE-002", "J-SMOKE-003"
        events = [
            {
                "platform": "pdd",
                "order_sn": ref_p,
                "status": "SHIPPED",
                "lines": [
                    {
                        "item_id": 1,
                        "warehouse_id": 1,
                        "batch_code": "B-1",
                        "qty": 2,
                    }
                ],
            },
            {
                "platform": "taobao",
                "tid": ref_t,
                "trade_status": "WAIT_BUYER_CONFIRM_GOODS",
                "lines": [
                    {
                        "item_id": 2,
                        "warehouse_id": 1,
                        "batch_code": "B-2",
                        "qty": 5,
                    }
                ],
            },
            {
                "platform": "jd",
                "orderId": ref_j,
                "orderStatus": "DELIVERED",
                "lines": [
                    {
                        "item_id": 3,
                        "warehouse_id": 1,
                        "batch_code": "B-3",
                        "qty": 1,
                    }
                ],
            },
        ]

        await handle_event_batch(events, session=s)
        await s.commit()

        # ---------- 3) 校验 stocks 槽位存在 ----------
        rows = (
            await s.execute(
                text(
                    """
                SELECT item_id, qty
                  FROM stocks
                 WHERE warehouse_id = 1
                   AND item_id IN (1,2,3)
                 ORDER BY item_id
                """
                )
            )
        ).all()
        qtys = {r[0]: r[1] for r in rows}
        assert set(qtys.keys()) == {1, 2, 3}
        assert all(q >= 0 for q in qtys.values())

        # ---------- 4) 重放相同事件 → 应该仍然不抛异常 ----------
        await handle_event_batch(events, session=s)
        await s.commit()
