from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service import StockService

UTC = timezone.utc


def _norm_scope(scope: str | None) -> str:
    sc = (scope or "").strip().upper() or "PROD"
    if sc not in ("PROD", "DRILL"):
        raise ValueError("scope must be PROD|DRILL")
    return sc


async def _requires_batch(session: AsyncSession, item_id: int) -> bool:
    row = await session.execute(
        text("SELECT has_shelf_life FROM items WHERE id=:i LIMIT 1"),
        {"i": int(item_id)},
    )
    v = row.scalar_one_or_none()
    return bool(v is True)


async def _slot_code(session: AsyncSession, item_id: int) -> str | None:
    return "NEAR" if await _requires_batch(session, item_id) else None


async def _qty(session: AsyncSession, item_id: int, wh: int, code: str | None, *, scope: str = "PROD") -> int:
    sc = _norm_scope(scope)
    r = await session.execute(
        text(
            """
            SELECT qty
              FROM stocks
             WHERE scope = :scope
               AND item_id=:i
               AND warehouse_id=:w
               AND batch_code IS NOT DISTINCT FROM :c
            """
        ),
        {"scope": sc, "i": int(item_id), "w": int(wh), "c": code},
    )
    return int(r.scalar_one_or_none() or 0)


async def _ensure_stock_seed(
    session: AsyncSession,
    *,
    item_id: int,
    wh: int,
    code: str | None,
    qty: int,
    scope: str = "PROD",
) -> None:
    sc = _norm_scope(scope)
    svc = StockService()
    before = await _qty(session, item_id, wh, code, scope=sc)
    if before >= qty:
        return

    need = qty - before
    if code is None:
        await svc.adjust(
            session=session,
            scope=sc,
            item_id=int(item_id),
            warehouse_id=int(wh),
            delta=int(need),
            reason=MovementType.INBOUND,
            ref=f"UT-SEED-OUTCORE-{item_id}-{wh}-NULL",
            ref_line=1,
            occurred_at=datetime.now(UTC),
            batch_code=None,
        )
    else:
        await svc.adjust(
            session=session,
            scope=sc,
            item_id=int(item_id),
            warehouse_id=int(wh),
            delta=int(need),
            reason=MovementType.INBOUND,
            ref=f"UT-SEED-OUTCORE-{item_id}-{wh}-{code}",
            ref_line=1,
            occurred_at=datetime.now(UTC),
            batch_code=str(code),
            production_date=date.today(),
        )
    await session.commit()


@pytest.mark.asyncio
async def test_outbound_core_idem_and_insufficient(session: AsyncSession):
    svc = StockService()
    item_id, wh = 3003, 1
    code = await _slot_code(session, item_id)

    # ✅ 显式 seed，保证 before >= 1
    await _ensure_stock_seed(session, item_id=item_id, wh=wh, code=code, qty=10, scope="PROD")

    before = await _qty(session, item_id, wh, code, scope="PROD")
    assert before >= 1

    # 扣 1
    await svc.adjust(
        session=session,
        scope="PROD",
        item_id=item_id,
        delta=-1,
        reason=MovementType.OUTBOUND,
        ref="Q-OUTCORE-1",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code=code,
        warehouse_id=wh,
    )
    mid = await _qty(session, item_id, wh, code, scope="PROD")
    assert mid == before - 1

    # 同 ref/ref_line 幂等
    res = await svc.adjust(
        session=session,
        scope="PROD",
        item_id=item_id,
        delta=-1,
        reason=MovementType.OUTBOUND,
        ref="Q-OUTCORE-1",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code=code,
        warehouse_id=wh,
    )
    assert res.get("idempotent") is True

    # 不足：新世界观为 409 + Problem（HTTPException）
    remain = await _qty(session, item_id, wh, code, scope="PROD")
    with pytest.raises(HTTPException) as exc:
        await svc.adjust(
            session=session,
            scope="PROD",
            item_id=item_id,
            delta=-(remain + 1),
            reason=MovementType.OUTBOUND,
            ref="Q-OUTCORE-2",
            ref_line=1,
            occurred_at=datetime.now(UTC),
            batch_code=code,
            warehouse_id=wh,
        )

    assert exc.value.status_code == 409
    assert isinstance(exc.value.detail, dict)
    assert exc.value.detail.get("error_code") == "insufficient_stock"
