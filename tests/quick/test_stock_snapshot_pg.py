from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.jobs.snapshot import run_once
from app.services.ledger_writer import write_ledger

pytestmark = pytest.mark.asyncio


async def _ins_item_batch(
    session: AsyncSession,
    *,
    sku: str = "SNAP-1",
    wh_id: int = 1,
    batch_code: str = "SNAP-B1",
) -> tuple[int, int, str]:
    """
    v2 粒度种子：

    - items: 按 sku 插入；
    - warehouses: id = wh_id；
    - batches: (item_id, warehouse_id, batch_code, expiry_date)；
    - stocks:  (item_id, warehouse_id, batch_code, qty=0)。
    """
    # item
    await session.execute(
        text(
            """
            INSERT INTO items (sku, name)
            VALUES (:s, :n)
            ON CONFLICT (sku) DO NOTHING
            """
        ),
        {"s": sku, "n": sku},
    )
    row = await session.execute(
        text("SELECT id FROM items WHERE sku = :s"),
        {"s": sku},
    )
    item_id = int(row.scalar_one())

    # warehouse
    await session.execute(
        text(
            """
            INSERT INTO warehouses (id, name)
            VALUES (:w, 'WH-SNAP')
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"w": wh_id},
    )

    # batch
    await session.execute(
        text(
            """
            INSERT INTO batches (item_id, warehouse_id, batch_code, expiry_date)
            VALUES (:item_id, :w, :b, DATE '2026-12-31')
            ON CONFLICT (item_id, warehouse_id, batch_code) DO NOTHING
            """
        ),
        {"item_id": item_id, "w": wh_id, "b": batch_code},
    )

    # stock 槽位（初始 qty=0）
    await session.execute(
        text(
            """
            INSERT INTO stocks (item_id, warehouse_id, batch_code, qty)
            VALUES (:item_id, :w, :b, 0)
            ON CONFLICT (item_id, warehouse_id, batch_code)
            DO UPDATE SET qty = EXCLUDED.qty
            """
        ),
        {"item_id": item_id, "w": wh_id, "b": batch_code},
    )

    await session.commit()
    return item_id, wh_id, batch_code


async def _ins_stock(
    session: AsyncSession,
    *,
    item_id: int,
    wh_id: int,
    batch_code: str,
    qty: int,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO stocks (item_id, warehouse_id, batch_code, qty)
            VALUES (:item_id, :w, :b, :q)
            ON CONFLICT (item_id, warehouse_id, batch_code)
            DO UPDATE SET qty = EXCLUDED.qty
            """
        ),
        {"item_id": item_id, "w": wh_id, "b": batch_code, "q": qty},
    )


async def _snapshot_qty_column(session: AsyncSession) -> str:
    """检测 stock_snapshots 的数量列：优先 qty，其次 qty_on_hand。"""
    cols = await session.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='stock_snapshots'
            """
        )
    )
    names = {r[0] for r in cols.fetchall()}
    if "qty_on_hand" in names:
        return "qty_on_hand"
    if "qty" in names:
        return "qty"
    raise RuntimeError("stock_snapshots has neither 'qty_on_hand' nor 'qty' column")


async def _get_snapshot_qty(
    session: AsyncSession,
    *,
    cut: datetime,
    item_id: int,
    wh_id: int,
    batch_code: str,
) -> float:
    qcol = await _snapshot_qty_column(session)
    row = await session.execute(
        text(
            f"""
            SELECT {qcol}
            FROM stock_snapshots
            WHERE snapshot_date = :cut
              AND item_id       = :item_id
              AND warehouse_id  = :w
              AND batch_code    = :b
            """
        ),
        {
            "cut": cut.date(),
            "item_id": item_id,
            "w": wh_id,
            "b": batch_code,
        },
    )
    r = row.scalar()
    return float(r) if r is not None else 0.0


async def test_snapshot_idempotent(
    session: AsyncSession,
    async_engine: AsyncEngine,
):
    """
    快照幂等性验证（v2）：

    场景：
      - 现势 stocks.qty=5；
      - 当日窗口内一笔 +3 台账；
      - 对同一 cut（某日 00:00）跑 run_once 两次；
      - 期望 snapshot 对应的“当日增量”仍为 3.0，不会被重复累加。
    """
    item_id, wh_id, batch_code = await _ins_item_batch(session)
    await _ins_stock(
        session,
        item_id=item_id,
        wh_id=wh_id,
        batch_code=batch_code,
        qty=5,
    )
    await session.commit()

    # 窗口内 +3 台账
    t0 = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    t1 = t0 + timedelta(minutes=10)

    await write_ledger(
        session,
        warehouse_id=wh_id,
        item_id=item_id,
        batch_code=batch_code,
        reason="TEST",
        delta=3,
        after_qty=8,  # 5 + 3，值本身对 snapshot 逻辑影响不大
        ref="REF-A",
        ref_line=1,
        occurred_at=t1,
        trace_id=None,
    )
    await session.commit()

    # 跑“当日 00:00”切片（两次，幂等）
    cut = t0.replace(hour=0, minute=0, second=0, microsecond=0)
    await run_once(async_engine, grain="day", at=cut, prev=None)
    await run_once(async_engine, grain="day", at=cut, prev=None)

    qty = await _get_snapshot_qty(
        session,
        cut=cut,
        item_id=item_id,
        wh_id=wh_id,
        batch_code=batch_code,
    )
    assert qty == 3.0
