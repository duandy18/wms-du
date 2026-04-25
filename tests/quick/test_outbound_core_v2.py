from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.shared.enums import MovementType
from app.wms.stock.services.lots import ensure_internal_lot_singleton, ensure_lot_full
from app.wms.stock.services.stock_adjust import adjust_lot_impl

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
    return "NEAR" if await _requires_batch(session, item_id) else None


async def _qty(session: AsyncSession, item_id: int, wh: int, code: str | None) -> int:
    if code is None:
        r = await session.execute(
            text(
                """
                SELECT COALESCE(qty, 0)
                  FROM stocks_lot
                 WHERE item_id=:i
                   AND warehouse_id=:w
                   /* lot_id NOT NULL in DB: filter by lots.lot_code */
                 LIMIT 1
                """
            ),
            {"i": int(item_id), "w": int(wh)},
        )
        return int(r.scalar_one_or_none() or 0)

    r = await session.execute(
        text(
            """
            SELECT COALESCE(sl.qty, 0)
              FROM stocks_lot sl
              JOIN lots l ON l.id = sl.lot_id
             WHERE sl.item_id=:i
               AND sl.warehouse_id=:w
               AND l.lot_code = :c
             LIMIT 1
            """
        ),
        {"i": int(item_id), "w": int(wh), "c": str(code)},
    )
    return int(r.scalar_one_or_none() or 0)


async def _lot_id_for_slot(session: AsyncSession, *, item_id: int, wh: int, code: str | None) -> int:
    if code is None:
        return int(
            await ensure_internal_lot_singleton(
                session,
                item_id=int(item_id),
                warehouse_id=int(wh),
                source_receipt_id=None,
                source_line_no=None,
            )
        )

    prod = date.today()
    exp = prod + timedelta(days=365)
    return int(
        await ensure_lot_full(
            session,
            item_id=int(item_id),
            warehouse_id=int(wh),
            lot_code=str(code),
            production_date=prod,
            expiry_date=exp,
        )
    )


async def _write_delta(
    session: AsyncSession,
    *,
    item_id: int,
    wh: int,
    code: str | None,
    delta: int,
    reason: MovementType | str,
    ref: str,
    ref_line: int,
):
    lot_id = await _lot_id_for_slot(session, item_id=int(item_id), wh=int(wh), code=code)
    prod = date.today() if code is not None else None
    exp = (prod + timedelta(days=365)) if prod is not None else None
    return await adjust_lot_impl(
        session=session,
        item_id=int(item_id),
        warehouse_id=int(wh),
        lot_id=int(lot_id),
        delta=int(delta),
        reason=reason,
        ref=str(ref),
        ref_line=int(ref_line),
        occurred_at=datetime.now(UTC),
        meta=None,
        lot_code=code,
        production_date=prod,
        expiry_date=exp,
        trace_id=None,
        utc_now=lambda: datetime.now(UTC),
    )


async def _ensure_stock_seed(session: AsyncSession, *, item_id: int, wh: int, code: str | None, qty: int) -> None:
    before = await _qty(session, item_id, wh, code)
    if before >= qty:
        return

    need = qty - before
    await _write_delta(
        session,
        item_id=int(item_id),
        wh=int(wh),
        code=code,
        delta=int(need),
        reason=MovementType.INBOUND,
        ref=f"UT-SEED-OUTCORE-{item_id}-{wh}-{code or 'NULL'}",
        ref_line=1,
    )
    await session.commit()


@pytest.mark.asyncio
async def test_outbound_core_idem_and_insufficient(session: AsyncSession):
    item_id, wh = 3003, 1
    code = await _slot_code(session, item_id)

    # ✅ 显式 seed，保证 before >= 1
    await _ensure_stock_seed(session, item_id=item_id, wh=wh, code=code, qty=10)

    before = await _qty(session, item_id, wh, code)
    assert before >= 1

    # 扣 1
    await _write_delta(
        session,
        item_id=item_id,
        wh=wh,
        code=code,
        delta=-1,
        reason=MovementType.OUTBOUND,
        ref="Q-OUTCORE-1",
        ref_line=1,
    )
    mid = await _qty(session, item_id, wh, code)
    assert mid == before - 1

    # 同 ref/ref_line 幂等
    res = await _write_delta(
        session,
        item_id=item_id,
        wh=wh,
        code=code,
        delta=-1,
        reason=MovementType.OUTBOUND,
        ref="Q-OUTCORE-1",
        ref_line=1,
    )
    assert res.get("idempotent") is True

    # 不足：新世界观为 409 + Problem（HTTPException）
    remain = await _qty(session, item_id, wh, code)
    with pytest.raises(ValueError) as exc:
        await _write_delta(
            session,
            item_id=item_id,
            wh=wh,
            code=code,
            delta=-(remain + 1),
            reason=MovementType.OUTBOUND,
            ref="Q-OUTCORE-2",
            ref_line=1,
        )

    assert "insufficient stock" in str(exc.value).lower()
