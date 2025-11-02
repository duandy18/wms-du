import pytest
from sqlalchemy import text

pytestmark = pytest.mark.grp_scan


async def _exists(session, table: str) -> bool:
    sql = text(
        """
      SELECT 1
      FROM information_schema.tables
      WHERE table_schema='public' AND table_name=:t
    """
    )
    return (await session.execute(sql, {"t": table})).first() is not None


@pytest.mark.asyncio
async def test_pick_tables_exist(session):
    """验证三张任务拣货表是否存在"""
    for t in ("pick_tasks", "pick_task_lines", "pick_task_line_reservations"):
        assert await _exists(session, t), f"missing table: {t}"


@pytest.mark.asyncio
async def test_pickline_status_autoupdate(session):
    """验证 picked_qty 状态自动更新"""
    # 建任务头
    res = await session.execute(
        text("INSERT INTO pick_tasks (warehouse_id, ref) VALUES (1, 'T-DEMO') RETURNING id")
    )
    task_id = res.scalar_one()

    # 建任务行
    res2 = await session.execute(
        text(
            """
            INSERT INTO pick_task_lines (task_id, item_id, req_qty, picked_qty)
            VALUES (:tid, 3001, 5, 0)
            RETURNING id, status
        """
        ),
        {"tid": task_id},
    )
    line_id, status = res2.first()
    assert status == "OPEN"

    # 改 picked_qty=3 → 触发器应变 PARTIAL
    await session.execute(
        text("UPDATE pick_task_lines SET picked_qty=3 WHERE id=:id"), {"id": line_id}
    )
    new_status = (
        await session.execute(
            text("SELECT status FROM pick_task_lines WHERE id=:id"), {"id": line_id}
        )
    ).scalar_one()
    assert new_status == "PARTIAL"

    # 改 picked_qty=5 → 应变 DONE
    await session.execute(
        text("UPDATE pick_task_lines SET picked_qty=5 WHERE id=:id"), {"id": line_id}
    )
    final_status = (
        await session.execute(
            text("SELECT status FROM pick_task_lines WHERE id=:id"), {"id": line_id}
        )
    ).scalar_one()
    assert final_status == "DONE"

    # 检查任务头状态是否被聚合更新（允许多种状态口径）
    head_status = (
        await session.execute(text("SELECT status FROM pick_tasks WHERE id=:id"), {"id": task_id})
    ).scalar_one()
    assert head_status in ("READY", "ASSIGNED", "PICKING", "DONE")
