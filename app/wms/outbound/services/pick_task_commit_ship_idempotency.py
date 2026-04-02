# app/services/pick_task_commit_ship_idempotency.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession


async def load_existing_outbound_commit_trace_id(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ref: str,
) -> Optional[str]:
    row = (
        await session.execute(
            SA(
                """
                SELECT trace_id
                  FROM outbound_commits_v2
                 WHERE platform = :platform
                   AND shop_id  = :shop_id
                   AND ref      = :ref
                 ORDER BY created_at DESC, updated_at DESC
                 LIMIT 1
                """
            ),
            {"platform": platform, "shop_id": shop_id, "ref": ref},
        )
    ).first()
    if not row:
        return None
    try:
        return str(row[0]) if row[0] else None
    except Exception:
        return None


async def load_existing_outbound_commit_trace_id_or_none(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ref: str,
) -> Optional[str]:
    return await load_existing_outbound_commit_trace_id(session, platform=platform, shop_id=shop_id, ref=ref)


async def load_existing_outbound_commit_meta_or_none(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ref: str,
) -> Optional[Dict[str, Any]]:
    """
    幂等短路需要的“最小可观测元数据”：
      - trace_id
      - created_at（用于 committed_at）
    """
    row = (
        await session.execute(
            SA(
                """
                SELECT trace_id, created_at
                  FROM outbound_commits_v2
                 WHERE platform = :platform
                   AND shop_id  = :shop_id
                   AND ref      = :ref
                 ORDER BY created_at DESC, updated_at DESC
                 LIMIT 1
                """
            ),
            {"platform": platform, "shop_id": shop_id, "ref": ref},
        )
    ).first()

    if not row:
        return None

    trace_id = None
    created_at = None
    try:
        trace_id = str(row[0]) if row[0] else None
    except Exception:
        trace_id = None
    try:
        created_at = row[1]
    except Exception:
        created_at = None

    if not trace_id:
        return None

    out: Dict[str, Any] = {"trace_id": trace_id}
    if isinstance(created_at, datetime):
        out["created_at"] = created_at
    return out


def build_idempotent_ok_payload(
    *,
    task_id: int,
    warehouse_id: int,
    platform: str,
    shop_id: str,
    ref: str,
    trace_id: str,
) -> Dict[str, Any]:
    return {
        "status": "OK",
        "idempotent": True,
        "task_id": task_id,
        "warehouse_id": warehouse_id,
        "platform": platform,
        "shop_id": shop_id,
        "ref": ref,
        "trace_id": trace_id,
        "diff": {
            "task_id": task_id,
            "has_over": False,
            "has_under": False,
            "lines": [],
        },
    }


async def mark_task_done_inplace(*, task: Any, now: datetime) -> None:
    task.status = "DONE"
    task.updated_at = now
    for line in getattr(task, "lines", None) or []:
        line.status = "DONE"
        line.updated_at = now
