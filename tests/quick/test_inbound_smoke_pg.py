from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ledger_writer import write_ledger

pytestmark = pytest.mark.asyncio


async def _ensure_min_domain_v2(
    session: AsyncSession,
    *,
    warehouse_id: int = 1,
    item_id: int = 777,
    batch_code: str = "SMOKE-BATCH-001",
) -> None:
    """
    在 v2 世界下，确保最小域存在：
    - warehouses: id = warehouse_id
    - items     : id = item_id
    - stocks    : (warehouse_id, item_id, batch_code) 存在一行，qty 初始为 0
    """

    # 仓库（最小一行）
    await session.execute(
        text("INSERT INTO warehouses(id, name) VALUES (:w, :name) ON CONFLICT (id) DO NOTHING"),
        {"w": warehouse_id, "name": f"WH-{warehouse_id}"},
    )

    # 商品（最小一行）
    await session.execute(
        text(
            "INSERT INTO items(id, sku, name, unit) "
            "VALUES (:i, :sku, :name, 'bag') "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"i": item_id, "sku": f"SKU-{item_id}", "name": f"ITEM-{item_id}"},
    )

    # stocks 3D 槽位：warehouse + item + batch_code
    await session.execute(
        text(
            """
            INSERT INTO stocks (warehouse_id, item_id, batch_code, qty)
            VALUES (:w, :i, :b, 0)
            ON CONFLICT ON CONSTRAINT uq_stocks_item_wh_batch DO NOTHING
            """
        ),
        {"w": warehouse_id, "i": item_id, "b": batch_code},
    )

    await session.commit()


async def test_inbound_ledger_snapshot_smoke(session: AsyncSession):
    """
    v2 入库烟雾测试（最小闭环，stocks + ledger 一致性）：

    场景：
    1. 准备一个 (warehouse, item, batch_code) 的库存槽位，初始 qty = 0；
    2. 模拟入库 +5（直接更新 stocks）；
    3. 调用 ledger_writer.write_ledger 写一条 INBOUND 账本，after_qty 对齐 stocks；
    4. 断言：
       - stocks.qty == after_qty
       - 最新一条 ledger 记录的 reason/delta/after_qty 与期望一致。
    """

    WH, ITEM, BATCH = 1, 777, "SMOKE-BATCH-001"

    # 1) 确保最小域存在
    await _ensure_min_domain_v2(
        session,
        warehouse_id=WH,
        item_id=ITEM,
        batch_code=BATCH,
    )

    # 2) 读当前 qty（可能为 0）
    before = (
        await session.execute(
            text(
                """
                SELECT qty
                FROM stocks
                WHERE warehouse_id = :w AND item_id = :i AND batch_code = :b
                """
            ),
            {"w": WH, "i": ITEM, "b": BATCH},
        )
    ).scalar_one() or 0
    after = int(before) + 5

    # 3) 模拟入库 +5：直接改 stocks
    await session.execute(
        text(
            """
            UPDATE stocks
            SET qty = :after
            WHERE warehouse_id = :w AND item_id = :i AND batch_code = :b
            """
        ),
        {"after": after, "w": WH, "i": ITEM, "b": BATCH},
    )

    # 4) 写一条账本记录（通过正式的 ledger_writer，而不是硬编码列）
    await write_ledger(
        session,
        warehouse_id=WH,
        item_id=ITEM,
        batch_code=BATCH,
        reason="INBOUND",
        delta=5,
        after_qty=after,
        ref="SMOKE-INBOUND",
        ref_line=1,
        occurred_at=datetime.now(timezone.utc),
        trace_id=None,
    )

    await session.commit()

    # ✅ 断言 stocks 与 ledger 一致

    # stocks.qty 是否等于 after
    qty_now = (
        await session.execute(
            text(
                """
                SELECT qty
                FROM stocks
                WHERE warehouse_id = :w AND item_id = :i AND batch_code = :b
                """
            ),
            {"w": WH, "i": ITEM, "b": BATCH},
        )
    ).scalar_one()
    assert int(qty_now) == after

    # 最新一条 ledger 是否匹配
    row = (
        await session.execute(
            text(
                """
                SELECT reason, delta, after_qty
                FROM stock_ledger
                WHERE warehouse_id = :w
                  AND item_id = :i
                  AND batch_code = :b
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"w": WH, "i": ITEM, "b": BATCH},
        )
    ).first()

    assert (
        row is not None
        and row.reason == "INBOUND"
        and int(row.delta) == 5
        and int(row.after_qty) == after
    )
