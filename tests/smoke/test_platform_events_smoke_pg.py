# tests/smoke/test_platform_events_smoke_pg.py
import os
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from app.services.platform_events import handle_event_batch

ASYNC_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms",
).replace("postgresql+psycopg", "postgresql+asyncpg")


@pytest.mark.asyncio
async def test_smoke_multi_platform_end2end():
    """
    验证多平台事件 → 出库扣减 → 记账 → 幂等 → 异常落库 的端到端链路：
      1) 造维度与初始化库存（3 个 item）
      2) 发送多平台事件（PDD / Taobao / JD），带 lines 的 PAID 触发出库与记账
      3) 校验 stocks 扣减 & stock_ledger 记账
      4) 重放相同事件，验证幂等（不再扣减、不再新增记账）
      5) 发送未知平台事件，验证写入 event_error_log
    """
    eng = create_async_engine(ASYNC_URL, future=True)
    Session = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)

    async with Session() as s:
        # ---------- 1) 维度与初始库存 ----------
        await s.execute(text("INSERT INTO warehouses (id, name) VALUES (1,'WH-1') ON CONFLICT (id) DO NOTHING"))
        await s.execute(text("""
            INSERT INTO items (id, sku, name, unit)
            VALUES
              (1, 'SKU-1', 'ITEM-1', 'PCS'),
              (2, 'SKU-2', 'ITEM-2', 'PCS'),
              (3, 'SKU-3', 'ITEM-3', 'PCS')
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, unit = EXCLUDED.unit
        """))
        await s.execute(text("""
            INSERT INTO locations (id, warehouse_id, name)
            VALUES (1, 1, 'L-1')
            ON CONFLICT (id) DO NOTHING
        """))
        await s.execute(text("""
            INSERT INTO stocks (item_id, location_id, qty) VALUES
              (1, 1, 10),
              (2, 1, 20),
              (3, 1,  5)
            ON CONFLICT (item_id, location_id) DO UPDATE SET qty = EXCLUDED.qty
        """))
        await s.commit()

        # ---------- 2) 多平台事件 ----------
        ref_p, ref_t, ref_j = "P-SMOKE-001", "T-SMOKE-002", "J-SMOKE-003"
        events = [
            {
                "platform": "pdd",
                "order_sn": ref_p,
                "status": "PAID",
                "lines": [{"item_id": 1, "location_id": 1, "qty": 2}],
            },
            {
                "platform": "taobao",
                "tid": ref_t,
                "trade_status": "WAIT_SELLER_SEND_GOODS",
                "lines": [{"item_id": 2, "location_id": 1, "qty": 5}],
            },
            {
                "platform": "jd",
                "orderId": ref_j,
                "orderStatus": "PAID",
                "lines": [{"item_id": 3, "location_id": 1, "qty": 1}],
            },
            {
                "platform": "mystery",  # 用于触发异常落库
                "foo": "bar",
            },
        ]
        await handle_event_batch(events, session=s)
        await s.commit()

        # ---------- 3) 校验扣减与记账 ----------
        rows = (await s.execute(
            text("SELECT item_id, qty FROM stocks WHERE location_id=1 AND item_id IN (1,2,3)")
        )).all()
        qtys = {r[0]: r[1] for r in rows}
        assert qtys[1] == 8   # 10 - 2
        assert qtys[2] == 15  # 20 - 5
        assert qtys[3] == 4   #  5 - 1

        for ref in (ref_p, ref_t, ref_j):
            cnt = (await s.execute(
                text("SELECT COUNT(1) FROM stock_ledger WHERE reason='OUTBOUND' AND ref=:r"),
                {"r": ref},
            )).scalar_one()
            assert cnt == 1

        # ---------- 4) 重放相同事件 → 幂等 ----------
        await handle_event_batch(events, session=s)
        await s.commit()

        rows2 = (await s.execute(
            text("SELECT item_id, qty FROM stocks WHERE location_id=1 AND item_id IN (1,2,3)")
        )).all()
        qtys2 = {r[0]: r[1] for r in rows2}
        assert qtys2[1] == 8
        assert qtys2[2] == 15
        assert qtys2[3] == 4

        for ref in (ref_p, ref_t, ref_j):
            cnt2 = (await s.execute(
                text("SELECT COUNT(1) FROM stock_ledger WHERE reason='OUTBOUND' AND ref=:r"),
                {"r": ref},
            )).scalar_one()
            assert cnt2 == 1  # 未新增

        # ---------- 5) 异常日志写入（兼容新旧列名） ----------
        row = (await s.execute(
            text("SELECT platform, COALESCE(error_code, error_type) AS code FROM event_error_log ORDER BY id DESC LIMIT 1")
        )).first()
        assert row is not None
        platform, code = row[0], row[1]
        assert platform in ("mystery", "unknown")
        assert code is not None  # 有明确错误码（老库 error_type，新库 error_code）
