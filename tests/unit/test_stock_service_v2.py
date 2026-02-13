# tests/unit/test_stock_service_v2.py
from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
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
    return "NEAR" if await _requires_batch(session, item_id) else None


async def _qty(session: AsyncSession, item_id: int, wh: int, code: str | None) -> int:
    r = await session.execute(
        text(
            """
            SELECT qty
              FROM stocks
             WHERE item_id = :i
               AND warehouse_id = :w
               AND batch_code IS NOT DISTINCT FROM :c
            """
        ),
        {"i": int(item_id), "w": int(wh), "c": code},
    )
    v = r.scalar_one_or_none()
    return int(v or 0)


async def _ensure_stock_seed(session: AsyncSession, *, item_id: int, wh: int, code: str | None, qty: int) -> None:
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
            delta=int(need),
            reason=MovementType.INBOUND,
            ref=f"UT-SEED-{item_id}-{wh}-NULL",
            ref_line=1,
            occurred_at=now,
            batch_code=None,
            warehouse_id=int(wh),
        )
    else:
        await svc.adjust(
            session=session,
            item_id=int(item_id),
            delta=int(need),
            reason=MovementType.INBOUND,
            ref=f"UT-SEED-{item_id}-{wh}-{code}",
            ref_line=1,
            occurred_at=now,
            batch_code=str(code),
            production_date=date.today(),
            warehouse_id=int(wh),
        )
    await session.commit()


@pytest.mark.asyncio
async def test_adjust_inbound_auto_resolves_dates(session: AsyncSession):
    """
    入库在缺省日期时，会自动兜底并推导日期，而不是直接抛错：
    - 不传 production_date / expiry_date；
    - adjust 正常执行；
    - 返回结果中有 production_date；
    - 如果存在 expiry_date，则应满足 expiry_date >= production_date；
    - 库存按 delta 正确变化。
    """
    svc = StockService()

    # ✅ 使用明确批次受控商品（基线：item=3001 has_shelf_life=true）
    item_id = 3001
    wh = 1
    code = "B1"

    before = await _qty(session, item_id=item_id, wh=wh, code=code)

    res = await svc.adjust(
        session=session,
        item_id=item_id,
        delta=1,
        reason=MovementType.INBOUND,
        ref="UT-IN-1",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code=code,
        warehouse_id=wh,
        # 不传日期，应该自动兜底
    )

    after = await _qty(session, item_id=item_id, wh=wh, code=code)
    assert after == before + 1

    prod = res.get("production_date")
    exp = res.get("expiry_date")

    assert isinstance(prod, date)
    if exp is not None:
        assert exp >= prod


@pytest.mark.asyncio
async def test_adjust_outbound_requires_batch(session: AsyncSession):
    """出库必须指定批次（batch_code 不能为空）——仅针对批次受控商品。"""
    svc = StockService()

    with pytest.raises(HTTPException) as exc:
        await svc.adjust(
            session=session,
            item_id=3001,
            delta=-1,
            reason=MovementType.OUTBOUND,
            ref="UT-OUT-1",
            ref_line=1,
            occurred_at=datetime.now(UTC),
            batch_code="",
            warehouse_id=1,
        )

    assert exc.value.status_code == 422
    assert isinstance(exc.value.detail, dict)
    assert exc.value.detail.get("error_code") == "batch_required"


@pytest.mark.asyncio
async def test_adjust_idempotent(session: AsyncSession):
    """相同 (wh,item,batch_code_key,reason,ref,ref_line) 的入库应命中幂等。"""
    svc = StockService()

    # ✅ 使用明确批次受控商品，避免 item=1 世界观漂移
    item_id = 3001
    wh = 1
    code = "NEAR"
    now = datetime.now(UTC)

    await svc.adjust(
        session=session,
        item_id=item_id,
        delta=1,
        reason=MovementType.INBOUND,
        ref="UT-IN-2",
        ref_line=1,
        occurred_at=now,
        batch_code=code,
        production_date=date.today(),
        warehouse_id=wh,
    )

    res = await svc.adjust(
        session=session,
        item_id=item_id,
        delta=1,
        reason=MovementType.INBOUND,
        ref="UT-IN-2",
        ref_line=1,
        occurred_at=now,
        batch_code=code,
        production_date=date.today(),
        warehouse_id=wh,
    )
    assert res.get("applied") is False and res.get("idempotent") is True


@pytest.mark.asyncio
async def test_adjust_outbound_and_insufficient(session: AsyncSession):
    """
    出库正常扣减一次，第二次强制超量扣减应抛 409 Problem(insufficient_stock)。
    该测试不再依赖 conftest 的隐式基线库存，而是先 seed 目标槽位。
    """
    svc = StockService()
    item_id = 3003
    wh = 1
    code = await _slot_code(session, item_id)

    await _ensure_stock_seed(session, item_id=item_id, wh=wh, code=code, qty=10)

    before = await _qty(session, item_id=item_id, wh=wh, code=code)
    assert before >= 1

    r = await svc.adjust(
        session=session,
        item_id=item_id,
        delta=-1,
        reason=MovementType.OUTBOUND,
        ref="UT-OUT-2",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code=code,
        warehouse_id=wh,
    )
    assert r["after"] == before - 1

    remain = await _qty(session, item_id=item_id, wh=wh, code=code)
    with pytest.raises(HTTPException) as exc:
        await svc.adjust(
            session=session,
            item_id=item_id,
            delta=-(remain + 1),
            reason=MovementType.OUTBOUND,
            ref="UT-OUT-3",
            ref_line=1,
            occurred_at=datetime.now(UTC),
            batch_code=code,
            warehouse_id=wh,
        )

    assert exc.value.status_code == 409
    assert isinstance(exc.value.detail, dict)
    assert exc.value.detail.get("error_code") == "insufficient_stock"
