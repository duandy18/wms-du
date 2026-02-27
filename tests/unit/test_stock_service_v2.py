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


async def _ensure_supplier_lot(
    session: AsyncSession,
    *,
    wh: int,
    item_id: int,
    code: str,
) -> int:
    """
    确保存在一个最小合法 SUPPLIER lot，并返回 id。

    注意：lots 表对策略快照（item_*_snapshot）有 NOT NULL 护栏，
    因此插入 lots 必须从 items 真相源读取并冻结快照字段。
    """
    row = (
        await session.execute(
            text(
                """
                INSERT INTO lots(
                    warehouse_id,
                    item_id,
                    lot_code_source,
                    lot_code,
                    source_receipt_id,
                    source_line_no,
                    production_date,
                    expiry_date,
                    expiry_source,
                    -- required snapshots (NOT NULL)
                    item_lot_source_policy_snapshot,
                    item_expiry_policy_snapshot,
                    item_derivation_allowed_snapshot,
                    item_uom_governance_enabled_snapshot,
                    -- optional snapshots (nullable)
                    item_has_shelf_life_snapshot,
                    item_shelf_life_value_snapshot,
                    item_shelf_life_unit_snapshot,
                    item_uom_snapshot,
                    item_case_ratio_snapshot,
                    item_case_uom_snapshot
                )
                SELECT
                    :w,
                    :i,
                    'SUPPLIER',
                    :code,
                    NULL,
                    NULL,
                    CURRENT_DATE,
                    CURRENT_DATE + INTERVAL '365 day',
                    'EXPLICIT',
                    it.lot_source_policy,
                    it.expiry_policy,
                    it.derivation_allowed,
                    it.uom_governance_enabled,
                    it.has_shelf_life,
                    it.shelf_life_value,
                    it.shelf_life_unit,
                    it.uom,
                    it.case_ratio,
                    it.case_uom
                  FROM items it
                 WHERE it.id = :i
                ON CONFLICT (warehouse_id, item_id, lot_code_source, lot_code)
                WHERE lot_code_source = 'SUPPLIER'
                DO UPDATE SET expiry_date = EXCLUDED.expiry_date
                RETURNING id
                """
            ),
            {"w": int(wh), "i": int(item_id), "code": str(code)},
        )
    ).first()
    assert row is not None
    return int(row[0])


async def _qty(session: AsyncSession, item_id: int, wh: int, code: str | None) -> int:
    """
    Phase 4D：只读 lot-world（stocks_lot + lots），按 lot_code（展示码）汇总 qty。
    - code=None 表示 lot_id=NULL 槽位（lot_code=NULL）
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
    Phase 4D：用 lot-world 种子补足库存。
    - code=None → lot_id=None 槽位
    - code!=None → 确保 SUPPLIER lot 存在，并写入该 lot 槽位
    """
    svc = StockService()
    now = datetime.now(UTC)

    before = await _qty(session, item_id, wh, code)
    if before >= qty:
        return

    need = qty - before

    if code is None:
        await svc.adjust_lot(
            session=session,
            item_id=int(item_id),
            warehouse_id=int(wh),
            lot_id=None,
            delta=int(need),
            reason=MovementType.INBOUND,
            ref=f"UT-SEED-{item_id}-{wh}-NULL",
            ref_line=1,
            occurred_at=now,
            batch_code=None,
        )
    else:
        lot_id = await _ensure_supplier_lot(session, wh=int(wh), item_id=int(item_id), code=str(code))
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
            production_date=date.today(),
        )

    await session.commit()


@pytest.mark.asyncio
async def test_adjust_inbound_auto_resolves_dates(session: AsyncSession):
    """
    入库在缺省日期时，会自动兜底并推导日期，而不是直接抛错：
    - 不传 production_date / expiry_date；
    - adjust_lot 正常执行；
    - 返回结果中有 production_date；
    - 如果存在 expiry_date，则应满足 expiry_date >= production_date；
    - 库存按 delta 正确变化。
    """
    svc = StockService()

    item_id = 3001
    wh = 1
    code = "B1"

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
    """
    仍保留 batch-world 合同：出库必须指定批次（batch_code 不能为空）——仅针对批次受控商品。
    该测试验证 StockService.adjust 的 HTTPProblem 包装语义。
    """
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
    """相同 (wh,item,lot_id_key,batch_code_key,reason,ref,ref_line) 的入库应命中幂等。"""
    svc = StockService()

    item_id = 3001
    wh = 1
    code = "NEAR"
    now = datetime.now(UTC)

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
        production_date=date.today(),
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
        production_date=date.today(),
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

    r = await svc.adjust_lot(
        session=session,
        item_id=item_id,
        warehouse_id=wh,
        lot_id=None,
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
            lot_id=None,
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
    注意：lots 表有 NOT NULL snapshot 护栏，因此插入必须冻结快照。
    """
    row = await session.execute(
        text(
            """
            INSERT INTO lots(
                warehouse_id,
                item_id,
                lot_code_source,
                lot_code,
                source_receipt_id,
                source_line_no,
                production_date,
                expiry_date,
                expiry_source,
                -- required snapshots (NOT NULL)
                item_lot_source_policy_snapshot,
                item_expiry_policy_snapshot,
                item_derivation_allowed_snapshot,
                item_uom_governance_enabled_snapshot,
                -- optional snapshots (nullable)
                item_has_shelf_life_snapshot,
                item_shelf_life_value_snapshot,
                item_shelf_life_unit_snapshot,
                item_uom_snapshot,
                item_case_ratio_snapshot,
                item_case_uom_snapshot
            )
            SELECT
                :w,
                :i,
                'SUPPLIER',
                :code,
                NULL,
                NULL,
                CURRENT_DATE,
                CURRENT_DATE + INTERVAL '365 day',
                'EXPLICIT',
                it.lot_source_policy,
                it.expiry_policy,
                it.derivation_allowed,
                it.uom_governance_enabled,
                it.has_shelf_life,
                it.shelf_life_value,
                it.shelf_life_unit,
                it.uom,
                it.case_ratio,
                it.case_uom
              FROM items it
             WHERE it.id = :i
            ON CONFLICT (warehouse_id, item_id, lot_code_source, lot_code)
            WHERE lot_code_source = 'SUPPLIER'
            DO UPDATE SET expiry_date = EXCLUDED.expiry_date
            RETURNING id
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id), "code": str(lot_code)},
    )
    lot_id = row.scalar_one()
    return int(lot_id)


@pytest.mark.asyncio
async def test_adjust_rejects_lot_mismatch(session: AsyncSession):
    """
    当传入 lot_id 且 lot 的 (warehouse_id,item_id) 与请求不一致，必须拒绝（409 lot_mismatch）。
    这里保留对 batch-world adjust 的护栏包装（HTTPException）。
    """
    svc = StockService()
    wh = 1

    bad_lot_id = await _insert_supplier_lot(session, warehouse_id=wh, item_id=3003, lot_code="UT-LOT-BAD-1")
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await svc.adjust(
            session=session,
            item_id=3001,
            delta=1,
            reason=MovementType.INBOUND,
            ref="UT-LOT-MISMATCH-1",
            ref_line=1,
            occurred_at=datetime.now(UTC),
            batch_code="B-LOT",
            production_date=date.today(),
            warehouse_id=wh,
            lot_id=bad_lot_id,
        )

    assert exc.value.status_code == 409
    assert isinstance(exc.value.detail, dict)
    assert exc.value.detail.get("error_code") == "lot_mismatch"


@pytest.mark.asyncio
async def test_adjust_rejects_lot_not_found(session: AsyncSession):
    """当传入 lot_id 且 lot 不存在，必须拒绝（404 lot_not_found）。"""
    svc = StockService()
    wh = 1

    with pytest.raises(HTTPException) as exc:
        await svc.adjust(
            session=session,
            item_id=3001,
            delta=1,
            reason=MovementType.INBOUND,
            ref="UT-LOT-NOTFOUND-1",
            ref_line=1,
            occurred_at=datetime.now(UTC),
            batch_code="B-LOT2",
            production_date=date.today(),
            warehouse_id=wh,
            lot_id=99999999,
        )

    assert exc.value.status_code == 404
    assert isinstance(exc.value.detail, dict)
    assert exc.value.detail.get("error_code") == "lot_not_found"
