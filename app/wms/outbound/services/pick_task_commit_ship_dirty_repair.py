# app/services/pick_task_commit_ship_dirty_repair.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

UTC = timezone.utc


async def repair_dirty_done_if_needed(task: Any) -> bool:
    """
    脏数据纠偏（蓝皮书防御）：

    - task.status 已是 DONE（甚至 lines 也 DONE）
    - 但 outbound_commits_v2 没有记录（说明并未真正提交出库）
    - 必须把状态退回可提交态，保留 picked_qty 事实

    返回：是否发生了修改（便于 caller 决定是否 flush）
    """
    changed = False
    if str(getattr(task, "status", "")).upper() == "DONE":
        task.status = "PICKING"
        changed = True

    lines = getattr(task, "lines", None) or []
    for ln in lines:
        if str(getattr(ln, "status", "")).upper() == "DONE":
            ln.status = "OPEN"
            changed = True

    if changed:
        now = datetime.now(UTC)
        try:
            task.updated_at = now
        except Exception:
            pass
        for ln in lines:
            try:
                ln.updated_at = now
            except Exception:
                pass

    return changed
