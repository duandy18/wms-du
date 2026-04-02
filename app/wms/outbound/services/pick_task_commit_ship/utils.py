# app/services/pick_task_commit_ship/utils.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

UTC = timezone.utc


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def build_diff_details(diff_summary: Any) -> list[Dict[str, Any]]:
    diffs: list[Dict[str, Any]] = []
    for ln in diff_summary.lines:
        status = str(getattr(ln, "status", "") or "")
        if status not in ("OVER", "UNDER"):
            continue

        req_qty = int(getattr(ln, "req_qty", 0) or 0)
        picked_qty = int(getattr(ln, "picked_qty", 0) or 0)
        delta = int(getattr(ln, "delta", 0) or 0)

        detail: Dict[str, Any] = {
            "type": "diff",
            "path": f"diff[item_id={int(ln.item_id)}]",
            "item_id": int(ln.item_id),
            "req_qty": req_qty,
            "picked_qty": picked_qty,
            "reason": status,
        }
        if delta < 0:
            detail["missing_qty"] = int(-delta)
        elif delta > 0:
            detail["over_qty"] = int(delta)

        diffs.append(detail)

    return diffs


def count_temp_fact_lines(task: Any) -> int:
    n = 0
    for ln in getattr(task, "lines", None) or []:
        try:
            if getattr(ln, "order_id", None) is None and int(getattr(ln, "picked_qty", 0) or 0) > 0:
                n += 1
        except Exception:
            continue
    return int(n)


async def advisory_lock_outbound_commit(session: AsyncSession, *, platform: str, shop_id: str, ref: str) -> None:
    """
    事务级并发护栏：同一 (platform, shop_id, ref) 的 commit 串行化。
    这不改变任何业务概念，只是把竞态缝焊死。
    """
    key = f"outbound_commit:{platform}:{shop_id}:{ref}"
    await session.execute(SA("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": key})
