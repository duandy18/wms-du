# tests/test_phase3_three_books_return_commit.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.inventory_adjustment.return_inbound.services.return_task_service_impl import ReturnTaskServiceImpl
from app.wms.snapshot.services.snapshot_run import run_snapshot
from app.wms.stock.services.lots import ensure_lot_full
from app.wms.stock.services.stock_adjust import adjust_lot_impl
from app.wms.shared.services.three_books_consistency import verify_commit_three_books


UTC = timezone.utc


async def _pick_item_for_stock_in(session: AsyncSession) -> tuple[int, bool]:
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
        raise RuntimeError("测试库没有 items 种子数据，无法运行 Return commit 合同测试")
    return int(row2[0]), True


async def _ensure_supplier_lot(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_code: str,
    production_date,
    expiry_date,
) -> int:
    lot_id = await ensure_lot_full(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_code=str(lot_code),
        production_date=production_date,
        expiry_date=expiry_date,
    )
    return int(lot_id)


@pytest.mark.asyncio
async def test_phase3_return_commit_three_books_strict(session: AsyncSession):
    """
    Phase 3 合同测试（退货回仓 commit）：

    关键点：
    - create_for_order 只认 ledger 出库事实：必须先写 OUTBOUND_SHIP delta<0；
    - return_task_lines.lot_id 必须来自原出库 stock_ledger.lot_id；
    - return_task_lines.batch_code 仅是 lots.lot_code 展示快照；
    - return commit 必须使用同一个 lot_id 回仓，而不是靠 batch_code 二次反查。
    """
    now = datetime.now(UTC)

    svc = ReturnTaskServiceImpl()

    wh_id = 1
    item_id, may_need_expiry = await _pick_item_for_stock_in(session)
    batch_code = "B-PH3-RET"
    prod = now.date()
    exp = (prod + timedelta(days=30)) if may_need_expiry else None

    uniq = uuid4().hex[:10]
    trace_id = f"PH3-UT-TRACE-RET-{uniq}"

    lot_id = await _ensure_supplier_lot(
        session,
        warehouse_id=wh_id,
        item_id=item_id,
        lot_code=batch_code,
        production_date=prod,
        expiry_date=exp,
    )

    # 1) 入库造库存：+10。测试造数统一走 lot-only 原语。
    await adjust_lot_impl(
        session=session,
        item_id=int(item_id),
        warehouse_id=int(wh_id),
        lot_id=int(lot_id),
        delta=10,
        reason="RECEIPT",
        ref=f"UT:PH3:RET:IN:{uniq}",
        ref_line=1,
        occurred_at=now,
        meta={"sub_reason": "UT_STOCK_IN"},
        batch_code=batch_code,
        production_date=prod,
        expiry_date=exp,
        trace_id=trace_id,
        utc_now=lambda: datetime.now(UTC),
    )

    # 2) 出库制造出库事实（ReturnTask 依据 ledger.lot_id 反查 shipped）
    order_ref = f"UT:PH3:RET:ORDER:{uniq}"
    shipped_qty = 4

    await adjust_lot_impl(
        session=session,
        item_id=int(item_id),
        warehouse_id=int(wh_id),
        lot_id=int(lot_id),
        delta=-int(shipped_qty),
        reason="OUTBOUND_SHIP",
        ref=order_ref,
        ref_line=1,
        occurred_at=now,
        meta={"sub_reason": "ORDER_SHIP"},
        batch_code=batch_code,
        production_date=None,
        expiry_date=None,
        trace_id=trace_id,
        utc_now=lambda: datetime.now(UTC),
    )

    shipped_lot_row = (
        await session.execute(
            text(
                """
                SELECT lot_id
                  FROM stock_ledger
                 WHERE warehouse_id = :w
                   AND item_id = :i
                   AND ref = :ref
                   AND ref_line = 1
                   AND delta < 0
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {"w": wh_id, "i": item_id, "ref": order_ref},
        )
    ).first()
    assert shipped_lot_row is not None, "missing shipped ledger row"
    shipped_lot_id = int(shipped_lot_row[0])
    assert shipped_lot_id == int(lot_id)

    # 3) 创建回仓任务：任务行必须固化原出库 lot_id
    task = await svc.create_for_order(session, order_id=order_ref)
    assert task.status != "COMMITTED"
    assert int(task.warehouse_id) == wh_id
    assert task.lines and len(task.lines) >= 1

    task_line = None
    for x in task.lines or []:
        if int(x.item_id) == int(item_id):
            task_line = x
            break

    assert task_line is not None
    assert int(task_line.lot_id) == shipped_lot_id
    assert str(task_line.batch_code) == batch_code

    stored_task_line = (
        await session.execute(
            text(
                """
                SELECT rtl.lot_id, rtl.batch_code, lo.lot_code
                  FROM return_task_lines rtl
                  JOIN lots lo
                    ON lo.id = rtl.lot_id
                 WHERE rtl.id = :line_id
                """
            ),
            {"line_id": int(task_line.id)},
        )
    ).first()
    assert stored_task_line is not None
    assert int(stored_task_line[0]) == shipped_lot_id
    assert str(stored_task_line[1]) == str(stored_task_line[2]) == batch_code

    # 4) 录入回仓数量
    task = await svc.record_receive(session, task_id=int(task.id), item_id=item_id, qty=2)
    ln = None
    for x in task.lines or []:
        if int(x.item_id) == int(item_id):
            ln = x
            break
    assert ln is not None
    assert int(ln.lot_id) == shipped_lot_id
    assert int(ln.picked_qty or 0) == 2

    # 5) commit：回仓入库（service 内 enforce_three_books）
    committed = await svc.commit(
        session,
        task_id=int(task.id),
        trace_id=trace_id,
        occurred_at=now,
    )
    assert committed.status == "COMMITTED"

    # 6) 双保险：再跑一次快照 + 对本次回仓 key 做三账校验
    ln2 = None
    for x in committed.lines or []:
        if int(x.item_id) == int(item_id):
            ln2 = x
            break
    assert ln2 is not None
    assert int(ln2.lot_id) == shipped_lot_id
    ref_line = int(getattr(ln2, "id", 1) or 1)

    # ✅ 终态：stock_ledger 无 batch_code 列；用 (wh,item,ref,ref_line,delta>0) 定位回仓入库行
    row = (
        await session.execute(
            text(
                """
                SELECT id, reason, lot_id
                  FROM stock_ledger
                 WHERE warehouse_id=:w
                   AND item_id=:i
                   AND ref=:ref
                   AND ref_line=:rl
                   AND delta>0
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {"w": wh_id, "i": item_id, "ref": order_ref, "rl": ref_line},
        )
    ).first()
    assert row, "missing return-in ledger row"
    reason_val = str(row[1])
    lot_id_val = int(row[2])
    assert lot_id_val == shipped_lot_id

    await run_snapshot(session)
    await verify_commit_three_books(
        session,
        warehouse_id=wh_id,
        ref=order_ref,
        effects=[
            {
                "warehouse_id": wh_id,
                "item_id": item_id,
                "lot_id": lot_id_val,
                "lot_code": batch_code,
                "qty": 2,
                "ref": order_ref,
                "ref_line": ref_line,
                "reason": reason_val,
            }
        ],
        at=now,
    )
