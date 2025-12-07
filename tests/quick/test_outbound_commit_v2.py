import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.outbound_service import ship_commit


async def _qty(session: AsyncSession, item_id: int, wh: int, code: str) -> int:
    r = await session.execute(
        text("SELECT qty FROM stocks WHERE item_id=:i AND warehouse_id=:w AND batch_code=:c"),
        {"i": item_id, "w": wh, "c": code},
    )
    return int(r.scalar_one_or_none() or 0)


@pytest.mark.asyncio
async def test_outbound_idem_and_insufficient(session: AsyncSession):
    """
    v2 出库合同（quick）：

    场景：
      - 预置 item 3003 在仓 1、批次 NEAR，有库存 >=1；
      - 同一个 order_id=Q-OUT-1 重复 ship_commit 两次，只扣一次；
      - 另一单 Q-OUT-2 请求超量，返回结果中至少一行 status='INSUFFICIENT'。

    粒度：
      - 行维度必须是 (warehouse_id, item_id, batch_code, qty)。
    """
    item_id, wh, code = 3003, 1, "NEAR"
    before = await _qty(session, item_id, wh, code)
    assert before >= 1

    # 幂等（两次同一单据，不应重复扣减）
    order_id = "Q-OUT-1"
    lines = [{"item_id": item_id, "warehouse_id": wh, "batch_code": code, "qty": 1}]
    r1 = await ship_commit(session, order_id=order_id, lines=lines, warehouse_code="WH-1")
    r2 = await ship_commit(session, order_id=order_id, lines=lines, warehouse_code="WH-1")
    assert r1["status"] == "OK" and r2["status"] == "OK"

    mid = await _qty(session, item_id, wh, code)
    # 只扣一次
    assert mid == before - 1

    # 不足：同一仓/批次请求 9999，应返回至少一条 INSUFFICIENT
    r3 = await ship_commit(
        session,
        order_id="Q-OUT-2",
        lines=[{"item_id": item_id, "warehouse_id": wh, "batch_code": code, "qty": 9999}],
        warehouse_code="WH-1",
    )
    assert any(x.get("status") == "INSUFFICIENT" for x in r3.get("results", []))
