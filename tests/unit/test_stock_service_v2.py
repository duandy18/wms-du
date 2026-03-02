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
    Phase M-5 终态：
    - lots 只承载 identity + policy snapshots（不承载 production/expiry/expiry_source，也不承载 item_uom/case snapshot）
    - 不依赖 ON CONFLICT 的具体 unique/index：先查再插
    """
    lot_code = str(code).strip()
    if not lot_code:
        raise ValueError("lot_code required")

    row0 = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM lots
                 WHERE warehouse_id = :w
                   AND item_id = :i
                   AND lot_code_source = 'SUPPLIER'
                   AND lot_code = :code
                 LIMIT 1
                """
            ),
            {"w": int(wh), "i": int(item_id), "code": lot_code},
        )
    ).first()
    if row0 is not None:
        return int(row0[0])

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
              -- required snapshots (NOT NULL)
              item_lot_source_policy_snapshot,
              item_expiry_policy_snapshot,
              item_derivation_allowed_snapshot,
              item_uom_governance_enabled_snapshot,
              -- optional shelf-life snapshots (nullable)
              item_shelf_life_value_snapshot,
              item_shelf_life_unit_snapshot,
              created_at
            )
            SELECT
              :w,
              it.id,
              'SUPPLIER',
              :code,
              NULL,
              NULL,
              it.lot_source_policy,
              it.expiry_policy,
              it.derivation_allowed,
              it.uom_governance_enabled,
              it.shelf_life_value,
              it.shelf_life_unit,
              now()
            FROM items it
            WHERE it.id = :i
            """
        ),
        {"w": int(wh), "i": int(item_id), "code": lot_code},
    )

    row1 = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM lots
                 WHERE warehouse_id = :w
                   AND item_id = :i
                   AND lot_code_source = 'SUPPLIER'
                   AND lot_code = :code
                 LIMIT 1
                """
            ),
            {"w": int(wh), "i": int(item_id), "code": lot_code},
        )
    ).first()
    assert row1 is not None, {"msg": "failed to ensure supplier lot", "wh": wh, "item_id": item_id, "code": lot_code}
    return int(row1[0])


async def _ensure_internal_lot_for_test(session: AsyncSession, *, wh: int, item_id: int, ref: str) -> int:
    """
    Phase M-5 终态：非批次商品也必须落在一个真实 lot_id 上（不允许 NULL lot）。
    INTERNAL lot 约束：
    - lot_code_source='INTERNAL'
    - lot_code IS NULL
    - source_receipt_id/source_line_no NOT NULL（DB check）
    """
    r = await session.execute(
        text(
            """
            INSERT INTO inbound_receipts (
              warehouse_id,
              source_type,
              source_id,
              ref,
              trace_id,
              status,
              remark,
              occurred_at
            )
            VALUES (
              :w,
              'PO',
              NULL,
              :ref,
              NULL,
              'DRAFT',
              'UT internal lot source',
              now()
            )
            RETURNING id
            """
        ),
        {"w": int(wh), "ref": str(ref)},
    )
    receipt_id = int(r.scalar_one())

    lot_row = (
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
                  -- required snapshots (NOT NULL)
                  item_lot_source_policy_snapshot,
                  item_expiry_policy_snapshot,
                  item_derivation_allowed_snapshot,
                  item_uom_governance_enabled_snapshot,
                  -- optional shelf-life snapshots (nullable)
                  item_shelf_life_value_snapshot,
                  item_shelf_life_unit_snapshot,
                  created_at
                )
                SELECT
                  :w,
                  it.id,
                  'INTERNAL',
                  NULL,
                  :rid,
                  1,
                  it.lot_source_policy,
                  it.expiry_policy,
                  it.derivation_allowed,
                  it.uom_governance_enabled,
                  it.shelf_life_value,
                  it.shelf_life_unit,
                  now()
                FROM items it
                WHERE it.id = :i
                RETURNING id
                """
            ),
            {"w": int(wh), "i": int(item_id), "rid": int(receipt_id)},
        )
    ).first()
    assert lot_row is not None, {"msg": "failed to ensure internal lot", "wh": wh, "item_id": item_id}
    return int(lot_row[0])


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
    终态：lots 不再承载 production/expiry/单位快照，仅冻结 policy snapshots。
    """
    code = str(lot_code).strip()
    if not code:
        raise ValueError("lot_code required")

    row0 = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM lots
                 WHERE warehouse_id = :w
                   AND item_id = :i
                   AND lot_code_source = 'SUPPLIER'
                   AND lot_code = :code
                 LIMIT 1
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "code": code},
        )
    ).first()
    if row0 is not None:
        return int(row0[0])

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
              -- required snapshots (NOT NULL)
              item_lot_source_policy_snapshot,
              item_expiry_policy_snapshot,
              item_derivation_allowed_snapshot,
              item_uom_governance_enabled_snapshot,
              -- optional shelf-life snapshots (nullable)
              item_shelf_life_value_snapshot,
              item_shelf_life_unit_snapshot,
              created_at
            )
            SELECT
              :w,
              it.id,
              'SUPPLIER',
              :code,
              NULL,
              NULL,
              it.lot_source_policy,
              it.expiry_policy,
              it.derivation_allowed,
              it.uom_governance_enabled,
              it.shelf_life_value,
              it.shelf_life_unit,
              now()
            FROM items it
            WHERE it.id = :i
            RETURNING id
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id), "code": code},
    )
    lot_id = row.scalar_one()
    return int(lot_id)


@pytest.mark.asyncio
async def test_adjust_rejects_lot_mismatch(session: AsyncSession):
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
