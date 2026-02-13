# app/services/pick_task_commit_ship_apply.py
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.pick_task_commit_ship_apply_stock import apply_stock_deductions_impl

_VALID_SCOPES = {"PROD", "DRILL"}


def _norm_scope(scope: Optional[str]) -> str:
    sc = (scope or "").strip().upper() or "PROD"
    if sc not in _VALID_SCOPES:
        raise ValueError("scope must be PROD|DRILL")
    return sc


def build_agg_from_commit_lines(commit_lines: Any) -> Dict[Tuple[int, Optional[str]], int]:
    agg: Dict[Tuple[int, Optional[str]], int] = {}
    for line in commit_lines:
        key = (int(line.item_id), (line.batch_code or None))
        agg[key] = agg.get(key, 0) + int(line.picked_qty)
    return agg


async def apply_stock_deductions(
    session: AsyncSession,
    *,
    scope: str = "PROD",
    task_id: int,
    warehouse_id: int,
    order_ref: str,
    occurred_at,
    agg: Dict[Tuple[int, Optional[str]], int],
    trace_id: Optional[str],
) -> int:
    sc = _norm_scope(scope)
    return await apply_stock_deductions_impl(
        session,
        scope=sc,
        task_id=task_id,
        warehouse_id=warehouse_id,
        order_ref=order_ref,
        occurred_at=occurred_at,
        agg=agg,
        trace_id=trace_id,
    )


async def write_outbound_commit_v2(
    session: AsyncSession,
    *,
    scope: str = "PROD",
    platform: str,
    shop_id: str,
    ref: str,
    trace_id: str,
) -> Dict[str, Any]:
    """
    ✅ 并发下稳定真相：UPSERT + RETURNING
    - 插入成功：返回本次 trace_id + created_at
    - 冲突命中：不改 trace_id（保持历史真相），只 bump updated_at，并返回“已存在那条记录”的 trace_id/created_at
    """
    sc = _norm_scope(scope)
    row = (
        await session.execute(
            SA(
                """
                INSERT INTO outbound_commits_v2 (
                    scope,
                    platform,
                    shop_id,
                    ref,
                    state,
                    created_at,
                    updated_at,
                    trace_id
                )
                VALUES (
                    :scope,
                    :platform,
                    :shop_id,
                    :ref,
                    'COMPLETED',
                    now(),
                    now(),
                    :trace_id
                )
                ON CONFLICT (scope, platform, shop_id, ref) DO UPDATE
                SET
                    updated_at = now(),
                    trace_id   = outbound_commits_v2.trace_id
                RETURNING trace_id, created_at
                """
            ),
            {"scope": sc, "platform": platform, "shop_id": shop_id, "ref": ref, "trace_id": trace_id},
        )
    ).first()

    if not row:
        return {"trace_id": str(trace_id), "created_at": None}

    tid = row[0]
    created_at = row[1]
    return {"trace_id": str(tid) if tid else str(trace_id), "created_at": created_at}
