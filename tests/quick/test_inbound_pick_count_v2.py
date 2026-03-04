from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service import StockService

UTC = timezone.utc


async def _ensure_internal_lot(session: AsyncSession, *, item_id: int, wh: int, ref: str) -> int:
    """
    Lot-World 终态：lot_id 是库存唯一身份。
    “非批次商品的 NULL 槽位”由 INTERNAL lot 承载（lot_code 可为 NULL，但 lot_id 必须真实存在）。
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
                :wh,
                'PO',
                NULL,
                :ref,
                NULL,
                'DRAFT',
                'UT internal lot source receipt',
                :occurred_at
            )
            RETURNING id
            """
        ),
        {"wh": wh, "ref": ref, "occurred_at": datetime.now(UTC)},
    )
    receipt_id = int(r.scalar_one())

    r2 = await session.execute(
        text(
            """
            INSERT INTO lots (
                warehouse_id,
                item_id,
                lot_code_source,
                lot_code,
                source_receipt_id,
                source_line_no,
                created_at,
                item_shelf_life_value_snapshot,
                item_shelf_life_unit_snapshot,
                item_lot_source_policy_snapshot,
                item_expiry_policy_snapshot,
                item_derivation_allowed_snapshot,
                item_uom_governance_enabled_snapshot
            )
            SELECT
                :wh,
                i.id,
                'INTERNAL',
                NULL,
                :receipt_id,
                1,
                now(),
                i.shelf_life_value,
                i.shelf_life_unit,
                i.lot_source_policy,
                i.expiry_policy,
                i.derivation_allowed,
                i.uom_governance_enabled
            FROM items i
            WHERE i.id = :item_id
            RETURNING id
            """
        ),
        {"wh": wh, "item_id": item_id, "receipt_id": receipt_id},
    )
    lot_id = int(r2.scalar_one())
    return lot_id


async def _qty(session: AsyncSession, item_id: int, wh: int, lot_id: int) -> int:
    r = await session.execute(
        text(
            """
            SELECT COALESCE(qty, 0)
              FROM stocks_lot
             WHERE item_id=:i
               AND warehouse_id=:w
               AND lot_id=:lot
             LIMIT 1
            """
        ),
        {"i": item_id, "w": wh, "lot": lot_id},
    )
    return int(r.scalar_one_or_none() or 0)


@pytest.mark.asyncio
async def test_receive_then_pick_then_count(session: AsyncSession):
    svc = StockService()
    item_id = 1
    wh = 1

    # 本用例要测 NONE/internal-lot 语义：局部把该 item 改回 NONE
    await session.execute(
        text("UPDATE items SET expiry_policy='NONE'::expiry_policy WHERE id=:i"),
        {"i": int(item_id)},
    )
    await session.commit()

    lot_id = await _ensure_internal_lot(session, item_id=item_id, wh=wh, ref="UT-IPC-INTERNAL-RECEIPT-1")
    batch_code: str | None = None

    await svc.adjust(
        session=session,
        item_id=item_id,
        delta=2,
        reason=MovementType.INBOUND,
        ref="Q-IPC-1",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code=batch_code,
        lot_id=lot_id,
        production_date=date.today(),
        warehouse_id=wh,
    )
    q1 = await _qty(session, item_id, wh, lot_id)
    assert q1 >= 2

    await svc.adjust(
        session=session,
        item_id=item_id,
        delta=-1,
        reason=MovementType.OUTBOUND,
        ref="Q-IPC-2",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code=batch_code,
        lot_id=lot_id,
        warehouse_id=wh,
    )
    q2 = await _qty(session, item_id, wh, lot_id)
    assert q2 == q1 - 1

    remain = await _qty(session, item_id, wh, lot_id)
    delta = 1 - remain
    if delta != 0:
        await svc.adjust(
            session=session,
            item_id=item_id,
            delta=delta,
            reason=MovementType.COUNT,
            ref="Q-IPC-3",
            ref_line=1,
            occurred_at=datetime.now(UTC),
            batch_code=batch_code,
            lot_id=lot_id,
            production_date=date.today(),
            warehouse_id=wh,
        )
    q3 = await _qty(session, item_id, wh, lot_id)
    assert q3 == 1
