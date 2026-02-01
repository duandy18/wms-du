# tests/quick/test_outbound_pg.py — v2: warehouse + batch_code 口径
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.outbound_service import ship_commit
from app.services.stock_service import StockService

UTC = timezone.utc


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
    row = await session.execute(
        text(
            """
            SELECT COALESCE(qty, 0)
              FROM stocks
             WHERE item_id = :i
               AND warehouse_id = :w
               AND batch_code IS NOT DISTINCT FROM :c
            """
        ),
        {"i": int(item_id), "w": int(wh), "c": code},
    )
    v = row.scalar_one_or_none()
    return int(v or 0)


async def _ensure_stock_seed(session: AsyncSession, *, item_id: int, wh: int, code: str | None, qty: int) -> None:
    """
    强护栏下不要依赖 conftest 的“隐式基线库存”，测试自己把目标槽位 seed 到 qty。
    - code=None  => NULL 槽位
    - code=str   => 批次槽位（入库需日期）
    """
    svc = StockService()
    now = datetime.now(UTC)

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
            ref=f"UT-SEED-{item_id}-{wh}-NULL",
            ref_line=1,
            occurred_at=now,
            batch_code=None,
        )
    else:
        await svc.adjust(
            session=session,
            item_id=int(item_id),
            warehouse_id=int(wh),
            delta=int(need),
            reason=MovementType.INBOUND,
            ref=f"UT-SEED-{item_id}-{wh}-{code}",
            ref_line=1,
            occurred_at=now,
            batch_code=str(code),
            production_date=date.today(),
        )
    await session.commit()


@pytest.mark.asyncio
async def test_outbound_idempotency(session: AsyncSession):
    """
    出库幂等性（v2）：
    - 对同一 order_id + 同样 lines 提交两次；
    - 只扣减一次库存；
    - 第二次命中幂等，不再重复扣减。
    """
    item_id = 3003
    wh = 1
    code = await _slot_code(session, item_id)

    await _ensure_stock_seed(session, item_id=item_id, wh=wh, code=code, qty=10)

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

    r1 = await ship_commit(session, order_id=order_id, lines=lines, warehouse_code="WH-1")
    assert r1["status"] == "OK"
    assert r1["committed_lines"] == 1

    mid = await _qty(session, item_id, wh, code)
    assert mid == before - 1

    r2 = await ship_commit(session, order_id=order_id, lines=lines, warehouse_code="WH-1")
    assert r2["status"] == "OK"

    after = await _qty(session, item_id, wh, code)
    assert after == mid


@pytest.mark.asyncio
async def test_outbound_insufficient_stock(session: AsyncSession):
    """
    库存不足时的出库行为（v2）：
    - 把目标槽位 qty 清到 0；
    - 申请出库 1 件；
    - 结果中至少有一条行状态为 INSUFFICIENT；
    - 库存保持为 0。
    """
    item_id = 1
    wh = 1
    code = await _slot_code(session, item_id)

    # 先确保槽位存在，再把 qty 清到 0
    await _ensure_stock_seed(session, item_id=item_id, wh=wh, code=code, qty=1)

    await session.execute(
        text(
            """
            UPDATE stocks
               SET qty = 0
             WHERE item_id = :i
               AND warehouse_id = :w
               AND batch_code IS NOT DISTINCT FROM :c
            """
        ),
        {"i": int(item_id), "w": int(wh), "c": code},
    )
    await session.commit()

    order_id = "SO-INS-001"
    lines = [
        {
            "item_id": item_id,
            "batch_code": code,
            "qty": 1,
            "warehouse_id": wh,
        }
    ]
    r = await ship_commit(session, order_id=order_id, lines=lines, warehouse_code="WH-1")
    assert r["status"] == "OK"
    assert any(x.get("status") == "INSUFFICIENT" for x in r.get("results", []))

    qty = await _qty(session, item_id, wh, code)
    assert qty == 0
