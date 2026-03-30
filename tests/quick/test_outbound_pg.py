# tests/quick/test_outbound_pg.py — v2: warehouse + batch_code 口径
from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.outbound_service import ship_commit
from app.services.stock_service import StockService
from tests.services._helpers import ensure_store

UTC = timezone.utc


async def _requires_batch(session: AsyncSession, item_id: int) -> bool:
    """
    Phase M 第一阶段：测试也不再读取 has_shelf_life（镜像字段）。
    批次受控唯一真相源：items.expiry_policy == 'REQUIRED'
    """
    row = await session.execute(
        text("SELECT expiry_policy FROM items WHERE id=:i LIMIT 1"),
        {"i": int(item_id)},
    )
    v = row.scalar_one_or_none()
    return str(v or "").strip().upper() == "REQUIRED"


async def _slot_code(session: AsyncSession, item_id: int) -> str | None:
    # 批次受控 => 用 NEAR；非批次 => 强护栏口径用 NULL 槽位（lot_id IS NULL）
    return "NEAR" if await _requires_batch(session, item_id) else None


async def _ensure_order_ref_exists(session: AsyncSession, *, order_ref: str) -> None:
    parts = str(order_ref).split(":", 2)
    assert len(parts) == 3, f"invalid test order_ref: {order_ref}"
    platform, shop_id, ext_order_no = parts
    store_id = await ensure_store(
        session,
        platform=str(platform).upper(),
        shop_id=str(shop_id),
        name=f"UT-{str(platform).upper()}-{shop_id}",
    )
    await session.execute(
        text(
            """
            INSERT INTO orders(platform, shop_id, store_id, ext_order_no, status, created_at, updated_at)
            VALUES (:p, :sid, :store_id, :ext, 'CREATED', now(), now())
            ON CONFLICT ON CONSTRAINT uq_orders_platform_shop_ext DO UPDATE
              SET store_id = EXCLUDED.store_id,
                  updated_at = EXCLUDED.updated_at
            """
        ),
        {
            "p": str(platform).upper(),
            "sid": str(shop_id),
            "store_id": int(store_id),
            "ext": str(ext_order_no),
        },
    )
    await session.commit()


async def _qty(session: AsyncSession, item_id: int, wh: int, code: str | None) -> int:
    if code is None:
        row = await session.execute(
            text(
                """
                SELECT COALESCE(qty, 0)
                  FROM stocks_lot
                 WHERE item_id = :i
                   AND warehouse_id = :w
                   /* lot_id NOT NULL in DB: filter by lots.lot_code */
                 LIMIT 1
                """
            ),
            {"i": int(item_id), "w": int(wh)},
        )
        v = row.scalar_one_or_none()
        return int(v or 0)

    row = await session.execute(
        text(
            """
            SELECT COALESCE(sl.qty, 0)
              FROM stocks_lot sl
              JOIN lots l ON l.id = sl.lot_id
             WHERE sl.item_id = :i
               AND sl.warehouse_id = :w
               AND l.lot_code = :c
             LIMIT 1
            """
        ),
        {"i": int(item_id), "w": int(wh), "c": str(code)},
    )
    v = row.scalar_one_or_none()
    return int(v or 0)


async def _ensure_stock_seed(session: AsyncSession, *, item_id: int, wh: int, code: str | None, qty: int) -> None:
    """
    强护栏下不要依赖 conftest 的“隐式基线库存”，测试自己把目标槽位 seed 到 qty。
    - code=None  => NULL 槽位（lot_id IS NULL）
    - code=str   => 批次槽位（lot_code 展示码），入库需日期
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

    order_id = "UT:PH3:SO-IDEM-001"
    await _ensure_order_ref_exists(session, order_ref=order_id)
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
    - 把目标槽位 qty 清到 0（通过 ledger 写入口，不直写余额表）；
    - 申请出库 1 件；
    - 抛 409(outbound_commit_reject)，details.results 至少有一条行状态为 INSUFFICIENT；
    - 库存保持为 0。
    """
    item_id = 1
    wh = 1
    code = await _slot_code(session, item_id)

    # 先确保槽位存在，再把 qty 清到 0
    await _ensure_stock_seed(session, item_id=item_id, wh=wh, code=code, qty=1)

    cur = await _qty(session, item_id, wh, code)
    if cur != 0:
        svc = StockService()
        await svc.adjust(
            session=session,
            item_id=int(item_id),
            warehouse_id=int(wh),
            delta=int(-cur),
            reason=MovementType.COUNT,
            ref=f"UT-ZERO-{item_id}-{wh}-{code or 'NULL'}",
            ref_line=1,
            occurred_at=datetime.now(UTC),
            batch_code=code,
            production_date=date.today() if code is not None else None,
            expiry_date=None,
        )
        await session.commit()

    order_id = "UT:PH3:SO-INS-001"
    await _ensure_order_ref_exists(session, order_ref=order_id)
    lines = [
        {
            "item_id": item_id,
            "batch_code": code,
            "qty": 1,
            "warehouse_id": wh,
        }
    ]

    with pytest.raises(HTTPException) as ei:
        await ship_commit(session, order_id=order_id, lines=lines, warehouse_code="WH-1")

    e = ei.value
    assert e.status_code == 409
    detail = e.detail
    assert isinstance(detail, dict)
    assert detail.get("error_code") == "outbound_commit_reject"

    details = detail.get("details") or []
    assert details and isinstance(details[0], dict)
    results = details[0].get("results") or []
    assert any(x.get("status") == "INSUFFICIENT" for x in results)

    qty = await _qty(session, item_id, wh, code)
    assert qty == 0
