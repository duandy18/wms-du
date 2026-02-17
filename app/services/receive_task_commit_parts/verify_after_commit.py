# app/services/receive_task_commit_parts/verify_after_commit.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.snapshot_run import run_snapshot
from app.services.three_books_consistency import verify_receive_commit_three_books


async def verify_after_receive_commit(
    session: AsyncSession,
    *,
    warehouse_id: int,
    ref: str,
    effects: List[Dict[str, Any]],
    at: datetime,
) -> None:
    """
    commit 后置护栏：commit → 库存 → 快照 的强一致性验证（只覆盖 receive）。

    注意：
    - run_snapshot 不能 rollback 外层事务（snapshot_run.py 应已用 savepoint 处理）
    - effects 为空时不做任何事（保持快路径）
    """
    if not effects:
        return

    await run_snapshot(session)
    await verify_receive_commit_three_books(
        session,
        warehouse_id=int(warehouse_id),
        ref=str(ref),
        effects=effects,
        at=at,
    )
