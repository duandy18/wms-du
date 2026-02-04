# app/api/routers/pick_tasks_routes_create_common.py
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.pick_tasks_routes_common import load_order_meta_or_404
from app.services.print_jobs_service import enqueue_pick_list_job


async def enqueue_pick_list_print_job(
    session: AsyncSession,
    *,
    order_id: int,
    task_id: int,
    warehouse_id: int,
    lines: list[dict],
    trace_id: str | None,
) -> None:
    """
    手工触发的打印入口：幂等 enqueue pick_list print_job（可观测闭环）
    注意：这里只负责 enqueue，不负责“自动触发”。
    """
    om = await load_order_meta_or_404(session, order_id=int(order_id))
    pj_payload = {
        "kind": "pick_list",
        "platform": str(om.get("platform") or "").upper(),
        "shop_id": str(om.get("shop_id") or ""),
        "ext_order_no": str(om.get("ext_order_no") or ""),
        "order_id": int(order_id),
        "pick_task_id": int(task_id),
        "warehouse_id": int(warehouse_id),
        "lines": lines,
        "trace_id": (trace_id or om.get("trace_id")),
        "version": 1,
    }
    await enqueue_pick_list_job(session, ref_type="pick_task", ref_id=int(task_id), payload=pj_payload)
