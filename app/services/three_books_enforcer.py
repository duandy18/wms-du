# app/services/three_books_enforcer.py
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.snapshot_run import run_snapshot
from app.services.three_books_consistency import verify_commit_three_books


async def enforce_three_books(
    session: AsyncSession,
    *,
    ref: str,
    effects: List[Dict[str, Any]],
    at: datetime,
) -> None:
    """
    Phase 3：强一致尾门（通用）。

    - effects: [{warehouse_id,item_id,batch_code,qty,ref_line,...}]
      约定：qty 就是 delta（入库正数、出库负数、确认事件为 0）
    - 自动按 warehouse_id 分组（适配跨仓 commit）
    - 内部做：
      1) run_snapshot(session)
      2) verify_commit_three_books(...)（逐仓）

    失败即 raise：commit 不可能“成功但不一致”。
    """
    if not effects:
        return

    await run_snapshot(session)

    by_wh: dict[int, list[Dict[str, Any]]] = defaultdict(list)
    for e in effects:
        by_wh[int(e["warehouse_id"])].append(e)

    for wh_id, effs in by_wh.items():
        await verify_commit_three_books(
            session,
            warehouse_id=int(wh_id),
            ref=str(ref),
            effects=effs,
            at=at,
        )
