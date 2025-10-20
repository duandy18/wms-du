# tests/quick/test_outbound_concurrency_pg.py
import asyncio
import os
import uuid
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from app.services.outbound_service import OutboundService


@pytest.mark.asyncio
async def test_concurrent_paid_events_idempotent():
    """
    并发重放同一 ref 的带 lines 事件：
      - 仅扣减一次（qty=10 -> 6）
      - 仅一条 OUTBOUND 记账
      - outbound_commits 首次登记，其余幂等
    """
    url = os.getenv("DATABASE_URL", "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms").replace(
        "postgresql+psycopg", "postgresql+asyncpg"
    )
    eng = create_async_engine(url, future=True)
    Session = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)

    ref = f"P-CONCUR-{uuid.uuid4().hex[:8]}"
    print("REF:", ref)

    # 基线准备
    async with Session() as s:
        await s.execute(text("DELETE FROM stock_ledger WHERE ref LIKE 'P-CONCUR-%'"))
        await s.execute(text("DELETE FROM outbound_commits WHERE ref LIKE 'P-CONCUR-%'"))
        await s.execute(text("INSERT INTO warehouses (id, name) VALUES (1,'WH-1') ON CONFLICT (id) DO NOTHING"))
        await s.execute(text("""
            INSERT INTO items (id, sku, name, unit)
            VALUES (10, 'SKU-10', 'ITEM-10', 'PCS')
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, unit = EXCLUDED.unit
        """))
        await s.execute(text("""
            INSERT INTO locations (id, warehouse_id, name)
            VALUES (10, 1, 'L-10')
            ON CONFLICT (id) DO NOTHING
        """))
        await s.execute(text("""
            INSERT INTO stocks (item_id, location_id, qty)
            VALUES (10, 10, 10)
            ON CONFLICT (item_id, location_id) DO UPDATE SET qty = EXCLUDED.qty
        """))
        await s.commit()

    async def worker():
        async with Session() as s:
            task = {
                "platform": "pdd",
                "ref": ref,
                "state": "PAID",
                "lines": [{"item_id": 10, "location_id": 10, "qty": 4}],
            }
            await OutboundService.apply_event(task, session=s)
            await s.commit()

    # 并发 10 个任务
    await asyncio.gather(*[worker() for _ in range(10)])

    # 验证
    async with Session() as s:
        qty = (await s.execute(text(
            "SELECT qty FROM stocks WHERE item_id=10 AND location_id=10"
        ))).scalar_one()
        assert qty == 6, f"qty should be 6 after single commit, got {qty}"

        ledger_cnt = (await s.execute(text(
            "SELECT COUNT(1) FROM stock_ledger WHERE reason='OUTBOUND' AND ref=:r"
        ), {"r": ref})).scalar_one()
        assert ledger_cnt == 1, f"ledger count should be 1 for ref={ref}, got {ledger_cnt}"
