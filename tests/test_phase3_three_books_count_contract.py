# tests/test_phase3_three_books_count_contract.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.scan_handlers.count_handler import handle_count
from app.services.snapshot_run import run_snapshot
from app.services.stock_service import StockService
from app.services.three_books_consistency import verify_commit_three_books


async def _pick_item(session: AsyncSession) -> tuple[int, bool]:
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
        raise RuntimeError("测试库没有 items 种子数据，无法运行盘点合同测试")
    return int(row2[0]), True


@pytest.mark.asyncio
async def test_phase3_count_confirm_delta_zero_records_ledger(session: AsyncSession):
    utc = timezone.utc
    now = datetime.now(utc)

    stock = StockService()
    warehouse_id = 1
    item_id, may_need_expiry = await _pick_item(session)
    batch_code = "B-PH3-CNT"

    prod = now.date()
    exp = (prod + timedelta(days=30)) if may_need_expiry else None

    # 先造库存：+5
    await stock.adjust(
        session=session,
        scope="PROD",
        item_id=item_id,
        warehouse_id=warehouse_id,
        batch_code=batch_code,
        delta=5,
        reason="RECEIPT",
        ref="UT:PH3:CNT:IN",
        ref_line=1,
        occurred_at=now,
        production_date=prod,
        expiry_date=exp,
        meta={"sub_reason": "UT_STOCK_IN"},
    )

    # 盘点确认：actual==current（delta==0），也必须写账
    ref = "UT:PH3:COUNT:CONFIRM"
    payload = await handle_count(
        session,
        item_id=item_id,
        warehouse_id=warehouse_id,
        batch_code=batch_code,
        actual=5,
        ref=ref,
        production_date=prod,
        expiry_date=exp,
        trace_id="PH3-UT-TRACE-CNT",
    )
    assert payload["delta"] == 0

    await run_snapshot(session)
    await verify_commit_three_books(
        session,
        warehouse_id=warehouse_id,
        ref=ref,
        effects=[
            {
                "warehouse_id": warehouse_id,
                "item_id": item_id,
                "batch_code": batch_code,
                "qty": 0,
                "ref": ref,
                "ref_line": 1,
            }
        ],
        at=now,
    )


@pytest.mark.asyncio
async def test_phase3_count_adjust_delta_nonzero_updates_stock(session: AsyncSession):
    utc = timezone.utc
    now = datetime.now(utc)

    stock = StockService()
    warehouse_id = 1
    item_id, may_need_expiry = await _pick_item(session)
    batch_code = "B-PH3-CNT2"

    prod = now.date()
    exp = (prod + timedelta(days=30)) if may_need_expiry else None

    # 先造库存：+5
    await stock.adjust(
        session=session,
        scope="PROD",
        item_id=item_id,
        warehouse_id=warehouse_id,
        batch_code=batch_code,
        delta=5,
        reason="RECEIPT",
        ref="UT:PH3:CNT2:IN",
        ref_line=1,
        occurred_at=now,
        production_date=prod,
        expiry_date=exp,
        meta={"sub_reason": "UT_STOCK_IN"},
    )

    # 盘点调整：actual=7（delta=+2）
    ref = "UT:PH3:COUNT:ADJUST"
    payload = await handle_count(
        session,
        item_id=item_id,
        warehouse_id=warehouse_id,
        batch_code=batch_code,
        actual=7,
        ref=ref,
        production_date=prod,
        expiry_date=exp,
        trace_id="PH3-UT-TRACE-CNT2",
    )
    assert payload["delta"] == 2

    await run_snapshot(session)
    await verify_commit_three_books(
        session,
        warehouse_id=warehouse_id,
        ref=ref,
        effects=[
            {
                "warehouse_id": warehouse_id,
                "item_id": item_id,
                "batch_code": batch_code,
                "qty": 2,
                "ref": ref,
                "ref_line": 1,
            }
        ],
        at=now,
    )
