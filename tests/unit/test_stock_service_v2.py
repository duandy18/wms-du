# tests/unit/test_stock_service_v2.py
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service import StockService

UTC = timezone.utc


async def _qty(session: AsyncSession, item_id: int, wh: int, code: str) -> int:
    """读取当前库存数量。"""
    r = await session.execute(
        text(
            """
            SELECT qty
            FROM stocks
            WHERE item_id = :i
              AND warehouse_id = :w
              AND batch_code = :c
            """
        ),
        {"i": item_id, "w": wh, "c": code},
    )
    v = r.scalar_one_or_none()
    return int(v or 0)


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

    before = await _qty(session, item_id=1, wh=1, code="B1")

    res = await svc.adjust(
        session=session,
        item_id=1,
        delta=1,
        reason=MovementType.INBOUND,
        ref="UT-IN-1",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code="B1",
        warehouse_id=1,
    )

    after = await _qty(session, item_id=1, wh=1, code="B1")
    assert after == before + 1

    prod = res.get("production_date")
    exp = res.get("expiry_date")

    assert isinstance(prod, date)
    if exp is not None:
        assert exp >= prod


@pytest.mark.asyncio
async def test_adjust_outbound_requires_batch(session: AsyncSession):
    """出库必须指定批次（batch_code 不能为空）。"""
    svc = StockService()
    with pytest.raises(ValueError):
        await svc.adjust(
            session=session,
            item_id=1,
            delta=-1,
            reason=MovementType.OUTBOUND,
            ref="UT-OUT-1",
            ref_line=1,
            occurred_at=datetime.now(UTC),
            batch_code="",
            warehouse_id=1,
        )


@pytest.mark.asyncio
async def test_adjust_idempotent(session: AsyncSession):
    """相同 (wh,item,batch_code,reason,ref,ref_line) 的入库应命中幂等。"""
    svc = StockService()

    # 首次入库
    await svc.adjust(
        session=session,
        item_id=1,
        delta=1,
        reason=MovementType.INBOUND,
        ref="UT-IN-2",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code="NEAR",
        production_date=date.today(),
        warehouse_id=1,
    )

    # 第二次相同参数应幂等
    res = await svc.adjust(
        session=session,
        item_id=1,
        delta=1,
        reason=MovementType.INBOUND,
        ref="UT-IN-2",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code="NEAR",
        production_date=date.today(),
        warehouse_id=1,
    )
    assert res.get("applied") is False and res.get("idempotent") is True


@pytest.mark.asyncio
async def test_adjust_outbound_and_insufficient(session: AsyncSession):
    """
    出库正常扣减一次，第二次强制超量扣减应抛 ValueError。
    """
    svc = StockService()
    before = await _qty(session, item_id=3003, wh=1, code="NEAR")
    assert before >= 1

    # 第一次扣 1
    r = await svc.adjust(
        session=session,
        item_id=3003,
        delta=-1,
        reason=MovementType.OUTBOUND,
        ref="UT-OUT-2",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code="NEAR",
        warehouse_id=1,
    )
    assert r["after"] == before - 1

    # 第二次强制超量扣减（remain + 1）
    remain = await _qty(session, item_id=3003, wh=1, code="NEAR")
    with pytest.raises(ValueError):
        await svc.adjust(
            session=session,
            item_id=3003,
            delta=-(remain + 1),
            reason=MovementType.OUTBOUND,
            ref="UT-OUT-3",
            ref_line=1,
            occurred_at=datetime.now(UTC),
            batch_code="NEAR",
            warehouse_id=1,
        )
