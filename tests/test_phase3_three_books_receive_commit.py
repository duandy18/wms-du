# tests/test_phase3_three_books_receive_commit.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.snapshot_run import run_snapshot
from app.services.stock_service import StockService
from app.services.three_books_consistency import verify_receive_commit_three_books


async def _pick_test_item(session: AsyncSession) -> tuple[int, bool]:
    """
    尽量挑一个不需要有效期管理的商品（避免被业务校验噪音卡住）。
    若找不到，则退回任意一个 item（has_shelf_life=True 也行，测试会显式填 expiry_date）。
    """
    row = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM items
                 WHERE COALESCE(has_shelf_life, false) = false
                 ORDER BY id ASC
                 LIMIT 1
                """
            )
        )
    ).first()
    if row:
        return int(row[0]), False

    row2 = (await session.execute(text("SELECT id FROM items ORDER BY id ASC LIMIT 1"))).first()
    if not row2:
        raise RuntimeError("测试库没有 items 种子数据，无法运行 Phase 3 合同测试")
    return int(row2[0]), True


async def _insert_confirmed_receipt_with_line(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: str,
    qty_received: int,
    occurred_at: datetime,
    trace_id: str,
    expiry_date,
) -> int:
    receipt_id = int(
        (
            await session.execute(
                text(
                    """
                    INSERT INTO inbound_receipts (
                        warehouse_id,
                        supplier_id,
                        supplier_name,
                        source_type,
                        source_id,
                        ref,
                        trace_id,
                        status,
                        remark,
                        occurred_at,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :warehouse_id,
                        NULL,
                        NULL,
                        'PO',
                        NULL,
                        :ref,
                        :trace_id,
                        'CONFIRMED',
                        'UT-PH3',
                        :occurred_at,
                        NOW(),
                        NOW()
                    )
                    RETURNING id
                    """
                ),
                {
                    "warehouse_id": int(warehouse_id),
                    "ref": "RCPT-PH3-UT",
                    "trace_id": str(trace_id),
                    "occurred_at": occurred_at,
                },
            )
        ).scalar_one()
    )

    await session.execute(
        text(
            """
            INSERT INTO inbound_receipt_lines (
                receipt_id,
                line_no,
                po_line_id,
                item_id,
                item_name,
                item_sku,
                batch_code,
                production_date,
                expiry_date,
                qty_received,
                units_per_case,
                qty_units,
                unit_cost,
                line_amount,
                remark,
                created_at,
                updated_at
            )
            VALUES (
                :rid,
                1,
                NULL,
                :iid,
                'UT-ITEM',
                NULL,
                :bc,
                :pd,
                :ed,
                :q,
                1,
                :q_units,
                NULL,
                NULL,
                'UT-PH3-LINE',
                NOW(),
                NOW()
            )
            """
        ),
        {
            "rid": int(receipt_id),
            "iid": int(item_id),
            "bc": str(batch_code),
            "pd": occurred_at.date(),
            "ed": expiry_date,
            "q": int(qty_received),
            "q_units": int(qty_received),
        },
    )
    await session.flush()
    return receipt_id


@pytest.mark.asyncio
async def test_phase3_receive_commit_three_books_strict(session: AsyncSession):
    """
    Phase 3 合同测试（终态口径）：

    - 以 Receipt(CONFIRMED) 作为事实锚点（终态不再有旧执行层）
    - 以 StockService.adjust(INBOUND) 作为“入库落账动作”写入 ledger+stocks
    - snapshot(today) == stocks（至少对 touched keys）
    - verify_receive_commit_three_books 对 touched effects 做三账一致性校验
    """
    stock_svc = StockService()
    utc = timezone.utc
    now = datetime.now(utc)

    item_id, may_need_expiry = await _pick_test_item(session)

    batch_code = "B-PH3"
    scanned_qty = 5  # base-unit

    prod = now.date()
    exp = (prod + timedelta(days=30)) if may_need_expiry else None

    # 1) 写入 Receipt 事实（终态：CONFIRMED）
    await _insert_confirmed_receipt_with_line(
        session,
        warehouse_id=1,
        item_id=item_id,
        batch_code=batch_code,
        qty_received=scanned_qty,
        occurred_at=now,
        trace_id="PH3-UT-TRACE",
        expiry_date=exp,
    )

    # 2) 写入入库动作（ledger+stocks）
    ref = "RCPT-PH3-UT"
    await stock_svc.adjust(
        session=session,
        item_id=item_id,
        warehouse_id=1,
        delta=scanned_qty,
        reason=MovementType.INBOUND,
        ref=ref,
        ref_line=1,
        occurred_at=now,
        batch_code=batch_code,
        production_date=prod,
        expiry_date=exp,
    )

    # 3) 双保险：独立跑快照 + 三账一致性校验
    await run_snapshot(session)
    await verify_receive_commit_three_books(
        session,
        warehouse_id=1,
        ref=ref,
        effects=[
            {
                "warehouse_id": 1,
                "item_id": item_id,
                "batch_code": batch_code,
                "qty": scanned_qty,
                "ref": ref,
                "ref_line": 1,
            }
        ],
        at=now,
    )
