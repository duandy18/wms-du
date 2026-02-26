# tests/smoke/test_platform_events_smoke_pg.py
"""
多平台平台事件 → pipeline 冒烟测试（v2 schema 版）。
"""

import os
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.enums import MovementType
from app.services.platform_events import handle_event_batch
from app.services.stock_service import StockService

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

        # Phase 4E：不再直写 legacy stocks，统一走 ledger 写入口 seed
        svc = StockService()
        now = datetime.now(timezone.utc)
        await svc.adjust(
            session=s,
            warehouse_id=1,
            item_id=1,
            delta=10,
            reason=MovementType.INBOUND,
            ref="SMOKE-SEED-1",
            ref_line=1,
            occurred_at=now,
            batch_code="B-1",
            production_date=date.today(),
        )
        await svc.adjust(
            session=s,
            warehouse_id=1,
            item_id=2,
            delta=20,
            reason=MovementType.INBOUND,
            ref="SMOKE-SEED-2",
            ref_line=1,
            occurred_at=now,
            batch_code="B-2",
            production_date=date.today(),
        )
        await svc.adjust(
            session=s,
            warehouse_id=1,
            item_id=3,
            delta=5,
            reason=MovementType.INBOUND,
            ref="SMOKE-SEED-3",
            ref_line=1,
            occurred_at=now,
            batch_code="B-3",
            production_date=date.today(),
        )
        await s.commit()

        # ---------- 2) Phase 5：预置 orders（使 ship commit 可解析到 orders.id） ----------
        # 注意：事件里用的是 ext_order_no-only（如 P-SMOKE-001），Phase 5 第二刀要求先能解析到 orders.id。
        ref_p, ref_t, ref_j = "P-SMOKE-001", "T-SMOKE-002", "J-SMOKE-003"
        await s.execute(
            text(
                """
                INSERT INTO orders(platform, shop_id, ext_order_no)
                VALUES
                  ('PDD',    'SMOKE', :p),
                  ('TAOBAO', 'SMOKE', :t),
                  ('JD',     'SMOKE', :j)
                ON CONFLICT (platform, shop_id, ext_order_no) DO NOTHING
                """
            ),
            {"p": ref_p, "t": ref_t, "j": ref_j},
        )
        await s.commit()

        # ---------- 3) 多平台“已发货”事件 ----------
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

        # ---------- 4) 校验 lot-world 余额存在 ----------
        rows = (
            await s.execute(
                text(
                    """
                SELECT item_id, COALESCE(SUM(qty), 0) AS qty
                  FROM stocks_lot
                 WHERE warehouse_id = 1
                   AND item_id IN (1,2,3)
                 GROUP BY item_id
                 ORDER BY item_id
                """
                )
            )
        ).all()
        qtys = {int(r[0]): int(r[1]) for r in rows}
        assert set(qtys.keys()) == {1, 2, 3}
        assert all(q >= 0 for q in qtys.values())

        # ---------- 5) 重放相同事件 → 应该仍然不抛异常 ----------
        await handle_event_batch(events, session=s)
        await s.commit()
