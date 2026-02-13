# tests/test_phase3_three_books_return_commit.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.return_task_service_impl import ReturnTaskServiceImpl
from app.services.snapshot_run import run_snapshot
from app.services.stock_service import StockService
from app.services.three_books_consistency import verify_commit_three_books


async def _pick_item_for_stock_in(session: AsyncSession) -> tuple[int, bool]:
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
        raise RuntimeError("测试库没有 items 种子数据，无法运行 Return commit 合同测试")
    return int(row2[0]), True


@pytest.mark.asyncio
async def test_phase3_return_commit_three_books_strict(session: AsyncSession):
    """
    Phase 3 合同测试（退货回仓 commit）：

    关键点：
    - create_for_order 只认 ledger 出库事实：必须先写 OUTBOUND_SHIP delta<0
    - return commit 用同一个 ref=order_ref，但 ref_line 不是 1（用 ReturnTaskLine.id）
      因此校验必须用“真实落库 reason”，不能猜 MovementType.RETURN 的字符串值。

    重要：
    - order_ref 必须每次唯一，避免命中历史遗留未 COMMITTED 的 ReturnTask（跨测试污染）。
    """
    utc = timezone.utc
    now = datetime.now(utc)

    stock = StockService()
    svc = ReturnTaskServiceImpl(stock_svc=stock)

    wh_id = 1
    item_id, may_need_expiry = await _pick_item_for_stock_in(session)
    batch_code = "B-PH3-RET"
    prod = now.date()
    exp = (prod + timedelta(days=30)) if may_need_expiry else None

    uniq = uuid4().hex[:10]
    trace_id = f"PH3-UT-TRACE-RET-{uniq}"

    # 1) 入库造库存：+10
    await stock.adjust(
        session=session,
        item_id=item_id,
        warehouse_id=wh_id,
        batch_code=batch_code,
        delta=10,
        reason="RECEIPT",
        ref=f"UT:PH3:RET:IN:{uniq}",
        ref_line=1,
        occurred_at=now,
        production_date=prod,
        expiry_date=exp,
        trace_id=trace_id,
        meta={"sub_reason": "UT_STOCK_IN"},
    )

    # 2) 出库制造出库事实（ReturnTask 依据 ledger 反查 shipped）
    order_ref = f"UT:PH3:RET:ORDER:{uniq}"
    shipped_qty = 4

    await stock.adjust(
        session=session,
        item_id=item_id,
        warehouse_id=wh_id,
        batch_code=batch_code,
        delta=-shipped_qty,
        reason="OUTBOUND_SHIP",
        ref=order_ref,
        ref_line=1,
        occurred_at=now,
        trace_id=trace_id,
        meta={"sub_reason": "ORDER_SHIP"},
    )

    # 3) 创建回仓任务
    task = await svc.create_for_order(session, order_id=order_ref)
    assert task.status != "COMMITTED"
    assert int(task.warehouse_id) == wh_id
    assert task.lines and len(task.lines) >= 1

    # 4) 录入回仓数量
    task = await svc.record_receive(session, task_id=int(task.id), item_id=item_id, qty=2)
    ln = None
    for x in task.lines or []:
        if int(x.item_id) == int(item_id):
            ln = x
            break
    assert ln is not None
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
    ref_line = int(getattr(ln2, "id", 1) or 1)

    # 查回仓那条正 delta 的 reason，避免猜 MovementType.RETURN 的落库字符串
    row = (
        await session.execute(
            text(
                """
                SELECT reason
                  FROM stock_ledger
                 WHERE warehouse_id=:w AND item_id=:i AND batch_code=:c
                   AND ref=:ref AND ref_line=:rl AND delta>0
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {"w": wh_id, "i": item_id, "c": batch_code, "ref": order_ref, "rl": ref_line},
        )
    ).first()
    assert row, "missing return-in ledger row"
    reason_val = str(row[0])

    await run_snapshot(session)
    await verify_commit_three_books(
        session,
        warehouse_id=wh_id,
        ref=order_ref,
        effects=[
            {
                "warehouse_id": wh_id,
                "item_id": item_id,
                "batch_code": batch_code,
                "qty": 2,
                "ref": order_ref,
                "ref_line": ref_line,
                "reason": reason_val,
            }
        ],
        at=now,
    )
