import pytest

pytestmark = pytest.mark.grp_flow

from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.asyncio]


# ------------------ DB helpers ------------------
async def _exec(engine, sql: str, params: dict | None = None):
    async with AsyncSession(bind=engine, expire_on_commit=False) as s:
        await s.execute(text(sql), params or {})
        await s.commit()


async def _scalar(engine, sql: str, params: dict | None = None) -> int:
    async with AsyncSession(bind=engine, expire_on_commit=False) as s:
        res = await s.scalar(text(sql), params or {})
        return int(res or 0)


async def _ensure_wh_and_loc(engine, wh_id: int = 1, loc_id: int = 1):
    # 确保仓库与库位存在（不会重复创建）
    await _exec(
        engine,
        "INSERT INTO warehouses(id, name) VALUES(:w, 'WH-1') ON CONFLICT (id) DO NOTHING",
        {"w": wh_id},
    )
    await _exec(
        engine,
        "INSERT INTO locations(id, name, warehouse_id) VALUES(:l, 'LOC-1', :w) ON CONFLICT (id) DO NOTHING",
        {"l": loc_id, "w": wh_id},
    )


async def _sum_item_qty(engine, item_id: int) -> int:
    return await _scalar(
        engine,
        "SELECT COALESCE(SUM(qty),0) FROM stocks WHERE item_id=:i",
        {"i": item_id},
    )


# ------------------ 造货：固定落在仓1/位1 ------------------
async def _seed_two_batches(session, *, item_id: int, location_id: int = 1):
    from app.services.stock_service import StockService

    svc = StockService()
    today = date.today()
    for code, exp, qty in [
        ("FEFO-NEAR", today + timedelta(days=2), 7),
        ("FEFO-LATE", today + timedelta(days=30), 9),
    ]:
        await svc.adjust(
            session=session,
            item_id=item_id,
            location_id=location_id,
            batch_code=code,
            expiry_date=exp,
            delta=qty,
            reason="seed",
        )


def _uniq_ref(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


# ------------------ Tests ------------------
async def test_outbound_fefo_basic(session):
    """一步法出库：扣减总量正确。"""
    from app.services.outbound_service import OutboundService

    engine = session.bind
    wh, loc = 1, 1
    await _ensure_wh_and_loc(engine, wh_id=wh, loc_id=loc)

    item_id = 1001
    ref = _uniq_ref("SO-001")
    await _seed_two_batches(session, item_id=item_id, location_id=loc)
    before = await _sum_item_qty(engine, item_id)

    res = await OutboundService.commit(
        session,
        platform="pdd",
        shop_id="",
        ref=ref,
        warehouse_id=wh,
        lines=[{"line_no": "SO-001-1", "item_id": item_id, "location_id": loc, "qty": 8}],
    )
    assert isinstance(res, dict)

    after = await _sum_item_qty(engine, item_id)
    assert before - after == 8


async def test_outbound_idempotent_ship(session):
    """幂等：同一 ref 重放不重复扣减。"""
    from app.services.outbound_service import OutboundService

    engine = session.bind
    wh, loc = 1, 1
    await _ensure_wh_and_loc(engine, wh_id=wh, loc_id=loc)

    item_id = 1002
    ref = _uniq_ref("SO-002")
    await _seed_two_batches(session, item_id=item_id, location_id=loc)
    before = await _sum_item_qty(engine, item_id)

    # 首次
    res1 = await OutboundService.commit(
        session,
        platform="pdd",
        shop_id="",
        ref=ref,
        warehouse_id=wh,
        lines=[{"line_no": "SO-002-1", "item_id": item_id, "location_id": loc, "qty": 5}],
    )
    # 重放（同 ref）
    res2 = await OutboundService.commit(
        session,
        platform="pdd",
        shop_id="",
        ref=ref,
        warehouse_id=wh,
        lines=[{"line_no": "SO-002-1", "item_id": item_id, "location_id": loc, "qty": 5}],
    )

    # 断言幂等行为
    if isinstance(res1, dict) and "results" in res1:
        statuses = {r.get("status") for r in res1["results"]}
        assert "OK" in statuses
    if isinstance(res2, dict) and "results" in res2:
        statuses = {r.get("status") for r in res2["results"]}
        assert "IDEMPOTENT" in statuses

    after = await _sum_item_qty(engine, item_id)
    assert before - after == 5  # 只扣一次


async def test_outbound_ledger_consistency(session):
    """
    台账一致性：Σ(delta)==库存扣减，且无负库存。
    仅统计当前 ref 的台账，防止历史记录干扰。
    """
    from app.services.outbound_service import OutboundService

    engine = session.bind
    wh, loc = 1, 1
    await _ensure_wh_and_loc(engine, wh_id=wh, loc_id=loc)

    item_id = 1003
    ref = _uniq_ref("SO-003")
    await _seed_two_batches(session, item_id=item_id, location_id=loc)
    before = await _sum_item_qty(engine, item_id)

    await OutboundService.commit(
        session,
        platform="pdd",
        shop_id="",
        ref=ref,
        warehouse_id=wh,
        lines=[{"line_no": "SO-003-1", "item_id": item_id, "location_id": loc, "qty": 10}],
    )

    after = await _sum_item_qty(engine, item_id)
    delta_inv = before - after
    assert delta_inv == 10

    # 仅统计当前 ref 的台账
    sum_ledger = await _scalar(
        engine,
        "SELECT COALESCE(SUM(delta),0) FROM stock_ledger "
        "WHERE reason='OUTBOUND' AND item_id=:i AND ref=:r",
        {"i": item_id, "r": ref},
    )
    assert sum_ledger in (-10, -1 * 10)

    # 不允许负库存
    neg = await _scalar(engine, "SELECT COUNT(*) FROM stocks WHERE qty < 0")
    assert neg == 0
