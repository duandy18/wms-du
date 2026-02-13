import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.outbound_service import ship_commit
from app.services.stock_service import StockService


async def _requires_batch(session: AsyncSession, item_id: int) -> bool:
    row = await session.execute(
        text("SELECT has_shelf_life FROM items WHERE id=:i LIMIT 1"),
        {"i": int(item_id)},
    )
    v = row.scalar_one_or_none()
    return bool(v is True)


async def _slot_code(session: AsyncSession, item_id: int) -> str | None:
    # 批次受控 => 用 NEAR；非批次 => 强护栏口径用 NULL 槽位
    return "NEAR" if await _requires_batch(session, item_id) else None


async def _qty(session: AsyncSession, item_id: int, wh: int, code: str | None) -> int:
    r = await session.execute(
        text(
            """
            SELECT qty
              FROM stocks
             WHERE item_id=:i
               AND warehouse_id=:w
               AND batch_code IS NOT DISTINCT FROM :c
            """
        ),
        {"i": int(item_id), "w": int(wh), "c": code},
    )
    return int(r.scalar_one_or_none() or 0)


async def _ensure_stock_seed(session: AsyncSession, *, item_id: int, wh: int, code: str | None, qty: int) -> None:
    """
    强护栏下不要依赖 conftest 的隐式基线库存，测试必须显式 seed 目标槽位。
    """
    svc = StockService()
    before = await _qty(session, item_id, wh, code)
    if before >= qty:
        return

    need = qty - before
    if code is None:
        await svc.adjust(
            session=session,
            item_id=int(item_id),
            warehouse_id=int(wh),
            delta=int(need),
            reason=MovementType.INBOUND,
            ref=f"UT-SEED-QOUT-{item_id}-{wh}-NULL",
            ref_line=1,
            occurred_at=None,
            batch_code=None,
        )
    else:
        await svc.adjust(
            session=session,
            item_id=int(item_id),
            warehouse_id=int(wh),
            delta=int(need),
            reason=MovementType.INBOUND,
            ref=f"UT-SEED-QOUT-{item_id}-{wh}-{code}",
            ref_line=1,
            occurred_at=None,
            batch_code=str(code),
            production_date=None,  # allow auto fallback
            expiry_date=None,
        )
    await session.commit()


@pytest.mark.asyncio
async def test_outbound_idem_and_insufficient(session: AsyncSession):
    """
    v2 出库合同（quick）：

    场景：
      - item 3003 在仓 1 的“目标槽位”有库存 >=1；
      - 同一个 order_id=Q-OUT-1 重复 ship_commit 两次，只扣一次；
      - 另一单 Q-OUT-2 请求超量，返回至少一条 INSUFFICIENT。

    槽位口径（与后端 requires_batch 派生一致）：
      - 批次受控：batch_code='NEAR'
      - 非批次受控：batch_code=NULL
    """
    item_id, wh = 3003, 1
    code = await _slot_code(session, item_id)

    # ✅ 显式 seed，保证 before >= 1
    await _ensure_stock_seed(session, item_id=item_id, wh=wh, code=code, qty=10)

    before = await _qty(session, item_id, wh, code)
    assert before >= 1

    # 幂等（两次同一单据，不应重复扣减）
    order_id = "Q-OUT-1"
    lines = [{"item_id": item_id, "warehouse_id": wh, "batch_code": code, "qty": 1}]
    r1 = await ship_commit(session, order_id=order_id, lines=lines, warehouse_code="WH-1")
    r2 = await ship_commit(session, order_id=order_id, lines=lines, warehouse_code="WH-1")
    assert r1["status"] == "OK" and r2["status"] == "OK"

    mid = await _qty(session, item_id, wh, code)
    assert mid == before - 1

    # 不足：同一槽位请求超量
    r3 = await ship_commit(
        session,
        order_id="Q-OUT-2",
        lines=[{"item_id": item_id, "warehouse_id": wh, "batch_code": code, "qty": 9999}],
        warehouse_code="WH-1",
    )
    assert any(x.get("status") == "INSUFFICIENT" for x in r3.get("results", []))
