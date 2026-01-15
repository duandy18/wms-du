# tests/test_phase3_three_books_receive_commit.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inbound_service import InboundService
from app.services.receive_task_commit import commit as commit_receive_task
from app.services.snapshot_run import run_snapshot
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


@pytest.mark.asyncio
async def test_phase3_receive_commit_three_books_strict(session: AsyncSession):
    """
    Phase 3 MVP 合同测试：
    - commit 成功 => ledger(ref/ref_line) 存在且 delta 匹配
    - snapshot(today) == stocks（至少对 touched keys）
    """
    inbound_svc = InboundService()
    utc = timezone.utc
    now = datetime.now(utc)

    item_id, may_need_expiry = await _pick_test_item(session)

    batch_code = "B-PH3"
    scanned_qty = 5  # base-unit

    # 对可能需要有效期管理的商品：显式补齐 production/expiry，避免依赖 shelf_life 参数推算
    prod = now.date()
    exp = (prod + timedelta(days=30)) if may_need_expiry else None

    # 1) 准备最小 receive_task + line
    task_id = int(
        (
            await session.execute(
                text(
                    """
                    INSERT INTO receive_tasks (warehouse_id, source_type, status, created_at, updated_at)
                    VALUES (1, 'PO', 'DRAFT', NOW(), NOW())
                    RETURNING id
                    """
                )
            )
        ).scalar_one()
    )

    await session.execute(
        text(
            """
            INSERT INTO receive_task_lines (
                task_id, item_id, batch_code, scanned_qty,
                status,
                units_per_case,
                production_date, expiry_date,
                item_name
            )
            VALUES (
                :tid, :iid, :bc, :q,
                'DRAFT',
                1,
                :pd, :ed,
                'UT-ITEM'
            )
            """
        ),
        {
            "tid": task_id,
            "iid": item_id,
            "bc": batch_code,
            "q": scanned_qty,
            "pd": prod,
            "ed": exp,
        },
    )

    await session.flush()

    # 2) 执行 commit（内部已做：run_snapshot + verify_receive_commit_three_books）
    task = await commit_receive_task(
        session,
        inbound_svc=inbound_svc,
        task_id=task_id,
        trace_id="PH3-UT-TRACE",
        occurred_at=now,
        utc=utc,
    )

    assert task.status == "COMMITTED"

    # 3) 双保险：再独立跑一次快照 + 校验
    await run_snapshot(session)
    await verify_receive_commit_three_books(
        session,
        warehouse_id=1,
        ref=f"RT-{task_id}",
        effects=[
            {
                "warehouse_id": 1,
                "item_id": item_id,
                "batch_code": batch_code,
                "qty": scanned_qty,
                "ref": f"RT-{task_id}",
                "ref_line": 1,
            }
        ],
        at=now,
    )
