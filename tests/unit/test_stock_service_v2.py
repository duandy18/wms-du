# tests/unit/test_stock_service_v2.py
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.shared.enums import MovementType
from app.wms.shared.services.lot_code_contract import validate_lot_code_contract
from app.wms.stock.services.lots import ensure_internal_lot_singleton, ensure_lot_full
from app.wms.stock.services.stock_service import StockService

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


def _required_lot_dates(requires_batch: bool) -> tuple[date | None, date | None]:
    if not requires_batch:
        return None, None
    prod = date.today()
    return prod, prod + timedelta(days=365)


async def _ensure_supplier_lot(
    session: AsyncSession,
    *,
    wh: int,
    item_id: int,
    code: str,
) -> int:
    """
    终态：SUPPLIER lot 创建必须走 ensure_lot_full。

    当前 REQUIRED lot 身份已经切到 (warehouse_id, item_id, production_date)，
    因此测试种子在 REQUIRED 商品下也必须显式给 production_date + expiry_date。
    """
    lot_code = str(code).strip()
    if not lot_code:
        raise ValueError("lot_code required")

    requires_batch = await _requires_batch(session, int(item_id))
    pd, ed = _required_lot_dates(requires_batch)

    return int(
        await ensure_lot_full(
            session,
            item_id=int(item_id),
            warehouse_id=int(wh),
            lot_code=str(lot_code),
            production_date=pd,
            expiry_date=ed,
        )
    )


async def _ensure_internal_lot_for_test(session: AsyncSession, *, wh: int, item_id: int, ref: str) -> int:
    """
    Phase M-5 终态：非批次商品也必须落在一个真实 lot_id 上（不允许 NULL lot）。
    INTERNAL lot 终态：
    - singleton per (warehouse_id,item_id)
    - lot_code_source='INTERNAL'
    - lot_code IS NULL

    旧实现通过 inbound_receipts + INSERT lots 来满足 provenance/check；
    终态收口后：INTERNAL lot 不再以 receipt provenance 参与 identity，
    本测试只需拿到合法 INTERNAL singleton lot_id。
    """
    _ = ref
    return int(
        await ensure_internal_lot_singleton(
            session,
            item_id=int(item_id),
            warehouse_id=int(wh),
            source_receipt_id=None,
            source_line_no=None,
        )
    )


async def _qty(session: AsyncSession, item_id: int, wh: int, code: str | None) -> int:
    """
    Phase 4D：只读 lot-world（stocks_lot + lots），按 lot_code（展示码）汇总 qty。
    - code=None 表示 lot_code=NULL（INTERNAL lot）
    """
    r = await session.execute(
        text(
            """
            SELECT COALESCE(SUM(sl.qty), 0)
              FROM stocks_lot sl
              LEFT JOIN lots lo ON lo.id = sl.lot_id
             WHERE sl.item_id = :i
               AND sl.warehouse_id = :w
               AND lo.lot_code IS NOT DISTINCT FROM CAST(:c AS TEXT)
            """
        ),
        {"i": int(item_id), "w": int(wh), "c": code},
    )
    v = r.scalar_one_or_none()
    return int(v or 0)


async def _ensure_stock_seed(session: AsyncSession, *, item_id: int, wh: int, code: str | None, qty: int) -> None:
    """
    Phase 4D+：用 lot-world 种子补足库存。
    - code=None 也必须落到 INTERNAL lot_id（lot_code=NULL）
    - code!=None → SUPPLIER lot（lot_code=code）
    """
    svc = StockService()
    now = datetime.now(UTC)

    before = await _qty(session, item_id, wh, code)
    if before >= qty:
        return

    need = qty - before

    if code is None:
        lot_id = await _ensure_internal_lot_for_test(
            session,
            wh=int(wh),
            item_id=int(item_id),
            ref=f"UT-INTERNAL-LOT-{item_id}-{wh}-{int(now.timestamp()*1000)}",
        )
        await svc.adjust_lot(
            session=session,
            item_id=int(item_id),
            warehouse_id=int(wh),
            lot_id=int(lot_id),
            delta=int(need),
            reason=MovementType.INBOUND,
            ref=f"UT-SEED-{item_id}-{wh}-INTERNAL",
            ref_line=1,
            occurred_at=now,
            batch_code=None,
        )
    else:
        lot_id = await _ensure_supplier_lot(session, wh=int(wh), item_id=int(item_id), code=str(code))
        prod, exp = _required_lot_dates(True)
        await svc.adjust_lot(
            session=session,
            item_id=int(item_id),
            warehouse_id=int(wh),
            lot_id=int(lot_id),
            delta=int(need),
            reason=MovementType.INBOUND,
            ref=f"UT-SEED-{item_id}-{wh}-{code}",
            ref_line=1,
            occurred_at=now,
            batch_code=str(code),
            production_date=prod,
            expiry_date=exp,
        )

    await session.commit()


@pytest.mark.asyncio
async def test_adjust_inbound_auto_resolves_dates(session: AsyncSession):
    svc = StockService()

    item_id = 3001
    wh = 1
    code = "B1"
    prod, exp = _required_lot_dates(True)

    lot_id = await _ensure_supplier_lot(session, wh=wh, item_id=item_id, code=code)
    before = await _qty(session, item_id=item_id, wh=wh, code=code)

    res = await svc.adjust_lot(
        session=session,
        item_id=item_id,
        warehouse_id=wh,
        lot_id=lot_id,
        delta=1,
        reason=MovementType.INBOUND,
        ref="UT-IN-1",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code=code,
        production_date=prod,
        expiry_date=exp,
    )

    after = await _qty(session, item_id=item_id, wh=wh, code=code)
    assert after == before + 1

    res_prod = res.get("production_date")
    res_exp = res.get("expiry_date")
    assert res_prod == prod
    assert res_exp == exp


def test_lot_code_contract_requires_lot_code_for_required_item() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_lot_code_contract(requires_batch=True, lot_code="")

    assert exc.value.status_code == 422
    assert isinstance(exc.value.detail, dict)
    assert exc.value.detail.get("error_code") == "batch_required"


@pytest.mark.asyncio
async def test_adjust_idempotent(session: AsyncSession):
    svc = StockService()

    item_id = 3001
    wh = 1
    code = "NEAR"
    now = datetime.now(UTC)
    prod, exp = _required_lot_dates(True)

    lot_id = await _ensure_supplier_lot(session, wh=wh, item_id=item_id, code=code)

    await svc.adjust_lot(
        session=session,
        item_id=item_id,
        warehouse_id=wh,
        lot_id=lot_id,
        delta=1,
        reason=MovementType.INBOUND,
        ref="UT-IN-2",
        ref_line=1,
        occurred_at=now,
        batch_code=code,
        production_date=prod,
        expiry_date=exp,
    )

    res = await svc.adjust_lot(
        session=session,
        item_id=item_id,
        warehouse_id=wh,
        lot_id=lot_id,
        delta=1,
        reason=MovementType.INBOUND,
        ref="UT-IN-2",
        ref_line=1,
        occurred_at=now,
        batch_code=code,
        production_date=prod,
        expiry_date=exp,
    )
    assert res.get("applied") is False and res.get("idempotent") is True


@pytest.mark.asyncio
async def test_adjust_outbound_and_insufficient(session: AsyncSession):
    """
    出库正常扣减一次，第二次强制超量扣减应抛 409 Problem(insufficient_stock)。
    """
    svc = StockService()
    item_id = 3003
    wh = 1
    code = await _slot_code(session, item_id)

    await _ensure_stock_seed(session, item_id=item_id, wh=wh, code=code, qty=10)

    before = await _qty(session, item_id=item_id, wh=wh, code=code)
    assert before >= 1

    # ✅ 必须扣减“真实有库存的那个 lot 槽位”
    lot_row = (
        await session.execute(
            text(
                """
                SELECT sl.lot_id
                  FROM stocks_lot sl
                  LEFT JOIN lots lo ON lo.id = sl.lot_id
                 WHERE sl.warehouse_id = :w
                   AND sl.item_id = :i
                   AND sl.qty > 0
                   AND lo.lot_code IS NOT DISTINCT FROM CAST(:c AS TEXT)
                 ORDER BY sl.qty DESC, sl.lot_id ASC
                 LIMIT 1
                """
            ),
            {"w": int(wh), "i": int(item_id), "c": code},
        )
    ).first()
    assert lot_row is not None, {"msg": "no positive stocks_lot slot found", "item_id": item_id, "warehouse_id": wh, "code": code}
    lot_id = int(lot_row[0])

    r = await svc.adjust_lot(
        session=session,
        item_id=item_id,
        warehouse_id=wh,
        lot_id=int(lot_id),
        delta=-1,
        reason=MovementType.OUTBOUND,
        ref="UT-OUT-2",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code=code,
    )
    assert int(r["after"]) == int(before) - 1

    remain = await _qty(session, item_id=item_id, wh=wh, code=code)
    with pytest.raises(ValueError):
        await svc.adjust_lot(
            session=session,
            item_id=item_id,
            warehouse_id=wh,
            lot_id=int(lot_id),
            delta=-(int(remain) + 1),
            reason=MovementType.OUTBOUND,
            ref="UT-OUT-3",
            ref_line=1,
            occurred_at=datetime.now(UTC),
            batch_code=code,
        )


async def _insert_supplier_lot(session: AsyncSession, *, warehouse_id: int, item_id: int, lot_code: str) -> int:
    """
    用于构造“坏 lot_id”（lot_mismatch / not_found）测试场景。

    终态收口后不允许 tests 直接 INSERT INTO lots。
    这里通过 ensure_lot_full 造出一个合法 lot_id，再用于 mismatch 测试。
    """
    requires_batch = await _requires_batch(session, int(item_id))
    pd, ed = _required_lot_dates(requires_batch)

    return int(
        await ensure_lot_full(
            session,
            item_id=int(item_id),
            warehouse_id=int(warehouse_id),
            lot_code=str(lot_code),
            production_date=pd,
            expiry_date=ed,
        )
    )


@pytest.mark.asyncio
async def test_adjust_rejects_lot_mismatch(session: AsyncSession):
    """
    任务3 终态：
    - adjust() 不再接受 lot_id（合同入口只接受 batch_code）
    - lot_id 维度的写入/校验走 adjust_lot()（原语入口）
    """
    svc = StockService()
    wh = 1
    prod, exp = _required_lot_dates(True)

    bad_lot_id = await _insert_supplier_lot(session, warehouse_id=wh, item_id=3003, lot_code="UT-LOT-BAD-1")
    await session.commit()

    with pytest.raises(ValueError) as exc:
        await svc.adjust_lot(
            session=session,
            item_id=3001,
            warehouse_id=wh,
            lot_id=int(bad_lot_id),
            delta=1,
            reason=MovementType.INBOUND,
            ref="UT-LOT-MISMATCH-1",
            ref_line=1,
            occurred_at=datetime.now(UTC),
            batch_code="B-LOT",
            production_date=prod,
            expiry_date=exp,
        )

    assert "mismatch" in str(exc.value).lower() or "lot_mismatch" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_adjust_rejects_lot_not_found(session: AsyncSession):
    """
    任务3 终态：lot_id 原语入口用 adjust_lot()，不存在则 ValueError。
    """
    svc = StockService()
    wh = 1
    prod, exp = _required_lot_dates(True)

    with pytest.raises(ValueError) as exc:
        await svc.adjust_lot(
            session=session,
            item_id=3001,
            warehouse_id=wh,
            lot_id=99999999,
            delta=1,
            reason=MovementType.INBOUND,
            ref="UT-LOT-NOTFOUND-1",
            ref_line=1,
            occurred_at=datetime.now(UTC),
            batch_code="B-LOT2",
            production_date=prod,
            expiry_date=exp,
        )

    assert "not found" in str(exc.value).lower() or "lot_not_found" in str(exc.value).lower()
