# tests/test_phase3_three_books_count_contract.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.inventory_adjustment.count.contracts.count import CountRequest
from app.wms.inventory_adjustment.count.services.count_service import CountService
from app.wms.snapshot.services.snapshot_run import run_snapshot
from app.wms.stock.services.stock_service import StockService
from app.wms.shared.services.three_books_consistency import verify_commit_three_books


def _date_to_utc_datetime(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


async def _pick_item(session: AsyncSession) -> tuple[int, bool]:
    row = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM items
                 WHERE COALESCE(expiry_policy::text, 'NONE') <> 'REQUIRED'
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


def _build_count_request(
    *,
    item_id: int,
    warehouse_id: int,
    qty: int,
    ref: str,
    batch_code: str,
    occurred_at: datetime,
    production_date: date | None,
    expiry_date: date | None,
    requires_expiry: bool,
) -> CountRequest:
    payload: dict[str, object] = {
        "item_id": item_id,
        "warehouse_id": warehouse_id,
        "qty": qty,
        "ref": ref,
        "batch_code": batch_code,
        "occurred_at": occurred_at,
    }
    if requires_expiry:
        if production_date is not None:
            payload["production_date"] = _date_to_utc_datetime(production_date)
        if expiry_date is not None:
            payload["expiry_date"] = _date_to_utc_datetime(expiry_date)
    return CountRequest(**payload)


@pytest.mark.asyncio
async def test_phase3_count_confirm_delta_zero_records_ledger(session: AsyncSession):
    utc = timezone.utc
    now = datetime.now(utc)

    stock = StockService()
    service = CountService()
    warehouse_id = 1
    item_id, may_need_expiry = await _pick_item(session)
    batch_code = "B-PH3-CNT"

    prod = now.date()
    exp = (prod + timedelta(days=30)) if may_need_expiry else None

    # 先造库存：+5
    await stock.adjust(
        session=session,
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

    # 盘点确认：qty == current（delta == 0），也必须写账
    ref = "UT:PH3:COUNT:CONFIRM"
    payload = await service.submit(
        session,
        req=_build_count_request(
            item_id=item_id,
            warehouse_id=warehouse_id,
            qty=5,
            ref=ref,
            batch_code=batch_code,
            occurred_at=now,
            production_date=prod,
            expiry_date=exp,
            requires_expiry=may_need_expiry,
        ),
    )
    assert payload.ok is True
    assert int(payload.after) == 5
    assert payload.item_id == item_id
    assert payload.warehouse_id == warehouse_id
    assert payload.batch_code == batch_code

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
    service = CountService()
    warehouse_id = 1
    item_id, may_need_expiry = await _pick_item(session)
    batch_code = "B-PH3-CNT2"

    prod = now.date()
    exp = (prod + timedelta(days=30)) if may_need_expiry else None

    # 先造库存：+5
    await stock.adjust(
        session=session,
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

    # 盘点调整：qty = 7（delta = +2）
    ref = "UT:PH3:COUNT:ADJUST"
    payload = await service.submit(
        session,
        req=_build_count_request(
            item_id=item_id,
            warehouse_id=warehouse_id,
            qty=7,
            ref=ref,
            batch_code=batch_code,
            occurred_at=now,
            production_date=prod,
            expiry_date=exp,
            requires_expiry=may_need_expiry,
        ),
    )
    assert payload.ok is True
    assert int(payload.after) == 7
    assert payload.item_id == item_id
    assert payload.warehouse_id == warehouse_id
    assert payload.batch_code == batch_code

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
