# tests/test_phase3_three_books_count_contract.py
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.inventory_adjustment.count.contracts.count import CountRequest
from app.wms.inventory_adjustment.count.services.count_service import CountService
from app.wms.snapshot.services.snapshot_run import run_snapshot
from app.wms.shared.services.three_books_consistency import verify_commit_three_books
from tests.utils.ensure_minimal import set_stock_qty


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


async def _load_lot_dates_by_code(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_code: str,
) -> tuple[int, date | None, date | None]:
    row = (
        await session.execute(
            text(
                """
                SELECT id, production_date, expiry_date
                  FROM lots
                 WHERE warehouse_id = :warehouse_id
                   AND item_id = :item_id
                   AND lot_code_source = 'SUPPLIER'
                   AND lot_code = :lot_code
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {
                "warehouse_id": int(warehouse_id),
                "item_id": int(item_id),
                "lot_code": str(lot_code),
            },
        )
    ).first()

    if row is None:
        raise AssertionError(
            {
                "msg": "seeded supplier lot not found",
                "warehouse_id": int(warehouse_id),
                "item_id": int(item_id),
                "lot_code": str(lot_code),
            }
        )

    return int(row[0]), row[1], row[2]


async def _load_ledger_lot_id(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    ref: str,
    ref_line: int = 1,
) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT lot_id
                  FROM stock_ledger
                 WHERE warehouse_id = :warehouse_id
                   AND item_id = :item_id
                   AND ref = :ref
                   AND ref_line = :ref_line
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {
                "warehouse_id": int(warehouse_id),
                "item_id": int(item_id),
                "ref": str(ref),
                "ref_line": int(ref_line),
            },
        )
    ).first()

    if not row or row[0] is None:
        raise AssertionError(
            {
                "msg": "count ledger row must carry lot_id",
                "warehouse_id": int(warehouse_id),
                "item_id": int(item_id),
                "ref": str(ref),
                "ref_line": int(ref_line),
            }
        )

    return int(row[0])


def _build_count_request(
    *,
    item_id: int,
    warehouse_id: int,
    qty: int,
    ref: str,
    lot_code: str,
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
        "lot_code": lot_code,
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

    service = CountService()
    warehouse_id = 1
    item_id, may_need_expiry = await _pick_item(session)
    batch_code = "B-PH3-CNT"

    # 先造库存：+5。测试造数统一走 lot-only helper。
    await set_stock_qty(
        session,
        item_id=item_id,
        warehouse_id=warehouse_id,
        batch_code=batch_code,
        qty=5,
    )

    _seed_lot_id, prod, exp = await _load_lot_dates_by_code(
        session,
        warehouse_id=warehouse_id,
        item_id=item_id,
        lot_code=batch_code,
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
            lot_code=batch_code,
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
    assert payload.lot_code == batch_code

    lot_id = await _load_ledger_lot_id(
        session,
        warehouse_id=warehouse_id,
        item_id=item_id,
        ref=ref,
        ref_line=1,
    )

    await run_snapshot(session)
    await verify_commit_three_books(
        session,
        warehouse_id=warehouse_id,
        ref=ref,
        effects=[
            {
                "warehouse_id": warehouse_id,
                "item_id": item_id,
                "lot_id": lot_id,
                "lot_code": batch_code,
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

    service = CountService()
    warehouse_id = 1
    item_id, may_need_expiry = await _pick_item(session)
    batch_code = "B-PH3-CNT2"

    # 先造库存：+5。测试造数统一走 lot-only helper。
    await set_stock_qty(
        session,
        item_id=item_id,
        warehouse_id=warehouse_id,
        batch_code=batch_code,
        qty=5,
    )

    _seed_lot_id, prod, exp = await _load_lot_dates_by_code(
        session,
        warehouse_id=warehouse_id,
        item_id=item_id,
        lot_code=batch_code,
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
            lot_code=batch_code,
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
    assert payload.lot_code == batch_code

    lot_id = await _load_ledger_lot_id(
        session,
        warehouse_id=warehouse_id,
        item_id=item_id,
        ref=ref,
        ref_line=1,
    )

    await run_snapshot(session)
    await verify_commit_three_books(
        session,
        warehouse_id=warehouse_id,
        ref=ref,
        effects=[
            {
                "warehouse_id": warehouse_id,
                "item_id": item_id,
                "lot_id": lot_id,
                "lot_code": batch_code,
                "qty": 2,
                "ref": ref,
                "ref_line": 1,
            }
        ],
        at=now,
    )


def test_count_request_rejects_retired_batch_code_alias() -> None:
    try:
        CountRequest(
            item_id=910001,
            warehouse_id=1,
            qty=1,
            ref="ut:count:retired-batch-code-alias",
            batch_code="UT-COUNT-RETIRED-ALIAS",
        )
    except Exception as exc:
        assert "batch_code" in str(exc)
    else:
        raise AssertionError("CountRequest must reject retired batch_code alias")
