# tests/api/test_pick_tasks_print_job_contract.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.order_service import OrderService
from app.services.stock_service import StockService

pytestmark = pytest.mark.asyncio


async def _get_item_expiry_policy(session: AsyncSession, item_id: int) -> str:
    row = (
        await session.execute(
            text("SELECT expiry_policy FROM items WHERE id = :id LIMIT 1"),
            {"id": int(item_id)},
        )
    ).scalar_one_or_none()
    return str(row or "")


async def _item_requires_batch(session: AsyncSession, item_id: int) -> bool:
    """
    Phase M 第一阶段：测试也不再读取 has_shelf_life（镜像字段）。
    批次受控唯一真相源：items.expiry_policy == 'REQUIRED'
    """
    pol = await _get_item_expiry_policy(session, item_id)
    return pol.strip().upper() == "REQUIRED"


async def _ensure_supplier_lot(session: AsyncSession, *, wh_id: int, item_id: int, lot_code: str) -> int:
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
                    item_lot_source_policy_snapshot,
                    item_expiry_policy_snapshot,
                    item_derivation_allowed_snapshot,
                    item_uom_governance_enabled_snapshot,
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
                ON CONFLICT (warehouse_id, item_id, lot_code)
                WHERE lot_code IS NOT NULL
                DO UPDATE SET lot_code_source = EXCLUDED.lot_code_source
                RETURNING id
                """
            ),
            {"w": int(wh_id), "i": int(item_id), "code": str(lot_code)},
        )
    ).first()
    assert row is not None, "failed to ensure supplier lot"
    return int(row[0])


async def _ensure_internal_lot(session: AsyncSession, *, wh_id: int, item_id: int, ref: str) -> int:
    r = await session.execute(
        text(
            """
            INSERT INTO inbound_receipts (
                warehouse_id, source_type, source_id, ref, trace_id, status, remark, occurred_at, created_at, updated_at
            )
            VALUES (
                :wh, 'PO', NULL, :ref, NULL, 'DRAFT', 'UT internal lot source receipt', :occurred_at, now(), now()
            )
            RETURNING id
            """
        ),
        {"wh": int(wh_id), "ref": str(ref), "occurred_at": datetime.now(timezone.utc)},
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
                it.id,
                'INTERNAL',
                NULL,
                :rid,
                1,
                now(),
                it.shelf_life_value,
                it.shelf_life_unit,
                it.lot_source_policy,
                it.expiry_policy,
                it.derivation_allowed,
                it.uom_governance_enabled
            FROM items it
            WHERE it.id = :i
            RETURNING id
            """
        ),
        {"wh": int(wh_id), "i": int(item_id), "rid": int(receipt_id)},
    )
    return int(r2.scalar_one())


async def _seed_order_and_stock(session: AsyncSession) -> int:
    platform = "PDD"
    shop_id = "1"
    uniq = uuid4().hex[:10]
    ext_order_no = f"UT-PICK-PRINTJOB-{uniq}"
    trace_id = f"TRACE-{ext_order_no}"
    now = datetime.now(timezone.utc)

    result = await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        occurred_at=now,
        buyer_name="拣货打印合同测试",
        buyer_phone="13800000000",
        order_amount=100,
        pay_amount=100,
        items=[{"item_id": 1, "qty": 2}],
        address=None,
        extras=None,
        trace_id=trace_id,
    )
    order_id = int(result["id"])

    # 可拣货护栏
    await session.execute(
        text(
            """
            INSERT INTO order_fulfillment (
              order_id,
              planned_warehouse_id,
              actual_warehouse_id,
              fulfillment_status,
              blocked_reasons,
              updated_at
            )
            VALUES (
              :oid,
              NULL,
              1,
              'SERVICE_ASSIGNED',
              NULL,
              now()
            )
            ON CONFLICT (order_id) DO UPDATE
               SET actual_warehouse_id = EXCLUDED.actual_warehouse_id,
                   fulfillment_status  = EXCLUDED.fulfillment_status,
                   blocked_reasons     = NULL,
                   updated_at          = now()
            """
        ),
        {"oid": int(order_id)},
    )

    requires_batch = await _item_requires_batch(session, 1)
    batch_code = "BATCH-TEST-PRINTJOB" if requires_batch else None

    stock = StockService()
    prod = date.today()
    exp = prod + timedelta(days=365)

    if requires_batch:
        lot_id = await _ensure_supplier_lot(session, wh_id=1, item_id=1, lot_code=str(batch_code))
    else:
        lot_id = await _ensure_internal_lot(session, wh_id=1, item_id=1, ref=f"UT-INTERNAL-LOT-PRINTJOB-{uniq}")

    await stock.adjust_lot(
        session=session,
        item_id=1,
        warehouse_id=1,
        lot_id=int(lot_id),
        delta=10,
        reason=MovementType.RECEIPT,
        ref=f"SEED-STOCK-PRINTJOB-{uniq}",
        ref_line=1,
        occurred_at=now,
        batch_code=batch_code,
        production_date=(prod if requires_batch else None),
        expiry_date=(exp if requires_batch else None),
        trace_id=trace_id,
    )

    await session.commit()
    return order_id


async def test_pick_task_get_includes_print_job_summary(
    client: AsyncClient,
    session: AsyncSession,
):
    order_id = await _seed_order_and_stock(session)

    r1 = await client.post(
        f"/pick-tasks/manual-from-order/{order_id}",
        json={"warehouse_id": 1, "source": "ORDER", "priority": 100},
    )
    assert r1.status_code == 200, r1.text
    task = r1.json()
    task_id = int(task["id"])

    r2 = await client.get(f"/pick-tasks/{task_id}")
    assert r2.status_code == 200, r2.text
    body = r2.json()
    pj0 = body.get("print_job")
    assert pj0 is None, body

    r3 = await client.post(
        f"/pick-tasks/{task_id}/print-pick-list",
        json={"order_id": int(order_id)},
    )
    assert r3.status_code == 200, r3.text

    r4 = await client.get(f"/pick-tasks/{task_id}")
    assert r4.status_code == 200, r4.text
    body2 = r4.json()

    pj = body2.get("print_job")
    assert isinstance(pj, dict), body2
    assert pj.get("kind") == "pick_list", pj
    assert pj.get("ref_type") == "pick_task", pj
    assert int(pj.get("ref_id") or 0) == task_id, pj
    assert pj.get("status") in ("queued", "printed", "failed"), pj
