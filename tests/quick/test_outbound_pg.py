# tests/quick/test_outbound_pg.py — v2: warehouse + batch_code 口径
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.outbound_service import ship_commit


async def _qty(session: AsyncSession, item_id: int, wh: int, code: str) -> int:
    row = await session.execute(
        text(
            """
            SELECT COALESCE(qty, 0)
            FROM stocks
            WHERE item_id = :i
              AND warehouse_id = :w
              AND batch_code = :c
            """
        ),
        {"i": item_id, "w": wh, "c": code},
    )
    v = row.scalar_one_or_none()
    return int(v or 0)


@pytest.mark.asyncio
async def test_outbound_idempotency(session: AsyncSession):
    """
    出库幂等性（v2，按 (warehouse,item,batch_code) 口径）：

    - 对同一 order_id + (item_id, batch_code, qty, warehouse_id) 提交两次；
    - 只扣减一次库存；
    - 第二次命中幂等，不再重复扣减。
    """
    item_id = 3003
    wh = 1
    code = "NEAR"

    # 基线：应由 tests/conftest 基线写入 qty >= 1
    before = await _qty(session, item_id, wh, code)
    assert before >= 1

    order_id = "SO-IDEM-001"
    lines = [
        {
            "item_id": item_id,
            "batch_code": code,
            "qty": 1,
            "warehouse_id": wh,
        }
    ]

    # 首次提交
    r1 = await ship_commit(
        session,
        order_id=order_id,
        lines=lines,
        warehouse_code="WH-1",
    )
    assert r1["status"] == "OK"
    assert r1["committed_lines"] == 1

    mid = await _qty(session, item_id, wh, code)
    assert mid == before - 1

    # 重放同一单据（应命中幂等，不再扣减）
    r2 = await ship_commit(
        session,
        order_id=order_id,
        lines=lines,
        warehouse_code="WH-1",
    )
    assert r2["status"] == "OK"

    after = await _qty(session, item_id, wh, code)
    assert after == mid


@pytest.mark.asyncio
async def test_outbound_insufficient_stock(session: AsyncSession):
    """
    库存不足时的出库行为（v2）：

    - 主动把 (wh,item,batch_code) 的 qty 清到 0；
    - 申请出库 1 件；
    - 结果中至少有一条行状态为 INSUFFICIENT；
    - 库存保持为 0。
    """
    item_id = 1
    wh = 1
    code = "NEAR"

    # 把现有库存清到 0
    await session.execute(
        text(
            """
            UPDATE stocks
            SET qty = 0
            WHERE item_id = :i
              AND warehouse_id = :w
              AND batch_code = :c
            """
        ),
        {"i": item_id, "w": wh, "c": code},
    )

    # 申请 1 件，应返回 INSUFFICIENT
    order_id = "SO-INS-001"
    lines = [
        {
            "item_id": item_id,
            "batch_code": code,
            "qty": 1,
            "warehouse_id": wh,
        }
    ]
    r = await ship_commit(
        session,
        order_id=order_id,
        lines=lines,
        warehouse_code="WH-1",
    )
    assert r["status"] == "OK"
    assert any(x.get("status") == "INSUFFICIENT" for x in r.get("results", []))

    qty = await _qty(session, item_id, wh, code)
    assert qty == 0
