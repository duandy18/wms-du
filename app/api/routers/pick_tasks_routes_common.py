# app/api/routers/pick_tasks_routes_common.py
from __future__ import annotations

from typing import Optional

from fastapi import status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_problem
from app.api.routers.pick_tasks_schemas import PrintJobOut


async def load_latest_pick_list_print_job(session: AsyncSession, *, task_id: int) -> Optional[PrintJobOut]:
    row = (
        await session.execute(
            text(
                """
                SELECT
                    id,
                    kind,
                    ref_type,
                    ref_id,
                    status,
                    payload,
                    requested_at,
                    printed_at,
                    error,
                    created_at,
                    updated_at
                  FROM print_jobs
                 WHERE kind = 'pick_list'
                   AND ref_type = 'pick_task'
                   AND ref_id = :tid
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {"tid": int(task_id)},
        )
    ).mappings().first()

    if not row:
        return None

    return PrintJobOut(
        id=int(row["id"]),
        kind=str(row["kind"]),
        ref_type=str(row["ref_type"]),
        ref_id=int(row["ref_id"]),
        status=str(row["status"]),
        payload=dict(row["payload"] or {}),
        requested_at=row["requested_at"],
        printed_at=row["printed_at"],
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def load_order_meta_or_404(session: AsyncSession, *, order_id: int) -> dict:
    """
    Phase 5+：
    - orders 不再有 warehouse_id
    - 执行仓/计划仓事实统一在 order_fulfillment
    - 这里为了兼容调用方（打印/取单元信息），仍输出 warehouse_id 字段：
      warehouse_id = COALESCE(actual_warehouse_id, planned_warehouse_id)
    """
    row = (
        await session.execute(
            text(
                """
                SELECT
                  o.platform,
                  o.shop_id,
                  o.ext_order_no,
                  o.trace_id,
                  COALESCE(of.actual_warehouse_id, of.planned_warehouse_id) AS warehouse_id
                FROM orders o
                LEFT JOIN order_fulfillment of
                  ON of.order_id = o.id
                WHERE o.id = :oid
                LIMIT 1
                """
            ),
            {"oid": int(order_id)},
        )
    ).mappings().first()

    if not row:
        raise_problem(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="order_not_found",
            message="订单不存在。",
            details=[{"type": "resource", "path": "order_id", "order_id": int(order_id), "reason": "not_found"}],
        )

    return dict(row)
