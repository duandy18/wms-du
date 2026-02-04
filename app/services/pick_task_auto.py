# app/services/pick_task_auto.py
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.print_jobs_service import enqueue_pick_list_job


async def _get_order_by_ref(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
) -> Optional[Dict[str, Any]]:
    """
    一步到位迁移后：
    - orders 只保留订单头
    - 履约/仓库快照在 order_fulfillment
    这里返回的 key 仍保持兼容旧调用方：warehouse_id/service_warehouse_id/fulfillment_status
    """
    row = await session.execute(
        text(
            """
            SELECT
              o.id,
              o.platform,
              o.shop_id,
              o.ext_order_no,
              f.actual_warehouse_id AS warehouse_id,
              f.planned_warehouse_id AS service_warehouse_id,
              f.fulfillment_status,
              o.status,
              o.trace_id
            FROM orders o
            LEFT JOIN order_fulfillment f ON f.order_id = o.id
            WHERE o.platform = :p
              AND o.shop_id  = :s
              AND o.ext_order_no = :o
            LIMIT 1
            """
        ),
        {"p": platform.upper(), "s": shop_id, "o": ext_order_no},
    )
    rec = row.mappings().first()
    return dict(rec) if rec else None


async def ensure_pick_task_for_order_ref(
    session: AsyncSession,
    *,
    ref: str,
    warehouse_id: int,
    priority: int = 100,
    source: str = "SYSTEM",
) -> int:
    """
    幂等确保 pick_tasks 存在（强幂等、无竞态）：

    - 依赖 DB 侧唯一索引：uq_pick_tasks_ref_wh (ref, warehouse_id)
    - 使用 INSERT .. ON CONFLICT .. DO UPDATE RETURNING id
      这样不会抛 IntegrityError，也无需“先查再插”。
    """
    ref_norm = str(ref or "").strip()
    wh = int(warehouse_id)

    if not ref_norm:
        raise ValueError("pick_task.ref invalid: empty")

    ins = await session.execute(
        text(
            """
            INSERT INTO pick_tasks(ref, warehouse_id, source, priority, status, created_at, updated_at)
            VALUES (:ref, :wh, :source, :priority, 'READY', now(), now())
            ON CONFLICT (ref, warehouse_id)
            DO UPDATE SET
              updated_at = EXCLUDED.updated_at
            RETURNING id
            """
        ),
        {
            "ref": ref_norm,
            "wh": wh,
            "source": str(source or "SYSTEM"),
            "priority": int(priority),
        },
    )
    return int(ins.first()[0])


async def ensure_pick_task_lines_from_target_qty(
    session: AsyncSession,
    *,
    pick_task_id: int,
    order_id: int,
    target_qty: Mapping[int, int],
) -> int:
    """
    幂等写入 pick_task_lines（只写 req_qty）：
    - 如果同 task_id 已有该 item_id 的行，则不重复插入
    - 本窗口不做复杂 “更新 req_qty” 逻辑：订单变更属于后续课题
    """
    if not target_qty:
        return 0

    rows = await session.execute(
        text(
            """
            SELECT item_id
              FROM pick_task_lines
             WHERE task_id = :tid
            """
        ),
        {"tid": int(pick_task_id)},
    )
    existed = {int(r[0]) for r in rows.fetchall()}

    n = 0
    for item_id, qty in target_qty.items():
        item_id_i = int(item_id)
        qty_i = int(qty)
        if qty_i <= 0:
            continue
        if item_id_i in existed:
            continue

        await session.execute(
            text(
                """
                INSERT INTO pick_task_lines(
                    task_id, order_id, order_line_id,
                    item_id, req_qty, picked_qty,
                    status, prefer_pickface,
                    target_location_id, note,
                    created_at, updated_at, batch_code
                )
                VALUES (
                    :tid, :oid, NULL,
                    :item_id, :req_qty, 0,
                    'OPEN', true,
                    NULL, NULL,
                    now(), now(), NULL
                )
                """
            ),
            {
                "tid": int(pick_task_id),
                "oid": int(order_id),
                "item_id": item_id_i,
                "req_qty": qty_i,
            },
        )
        n += 1

    return n


async def enqueue_pick_list_print_job(
    session: AsyncSession,
    *,
    ref_type: str,
    ref_id: int,
    payload: Dict[str, Any],
) -> int:
    """
    幂等入队打印任务（强幂等、无竞态）：

    纯重构：收口到 print_jobs_service.enqueue_pick_list_job（行为不变）。
    """
    return await enqueue_pick_list_job(
        session,
        ref_type=str(ref_type or "").strip() or "pick_task",
        ref_id=int(ref_id),
        payload=payload,
    )


def build_pick_list_payload(
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
    order_id: int,
    pick_task_id: int,
    warehouse_id: int,
    target_qty: Mapping[int, int],
    trace_id: Optional[str],
) -> Dict[str, Any]:
    lines = [{"item_id": int(k), "req_qty": int(v)} for k, v in target_qty.items() if int(v) > 0]
    return {
        "kind": "pick_list",
        "platform": platform.upper(),
        "shop_id": shop_id,
        "ext_order_no": ext_order_no,
        "order_id": int(order_id),
        "pick_task_id": int(pick_task_id),
        "warehouse_id": int(warehouse_id),
        "lines": lines,
        "trace_id": trace_id,
        "version": 1,
    }


async def resolve_order_and_ensure_task_and_print(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
    ref: str,
    warehouse_id: int,
    order_id: int,
    target_qty: Mapping[int, int],
    trace_id: Optional[str],
) -> Dict[str, Any]:
    """
    单入口 orchestration：
      - ensure pick_task（幂等）
      - ensure pick_task_lines（幂等）
      - enqueue print_job(pick_list)（幂等）
    """
    pick_task_id = await ensure_pick_task_for_order_ref(
        session,
        ref=ref,
        warehouse_id=warehouse_id,
    )

    inserted_lines = await ensure_pick_task_lines_from_target_qty(
        session,
        pick_task_id=pick_task_id,
        order_id=order_id,
        target_qty=target_qty,
    )

    payload = build_pick_list_payload(
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        order_id=order_id,
        pick_task_id=pick_task_id,
        warehouse_id=warehouse_id,
        target_qty=target_qty,
        trace_id=trace_id,
    )

    print_job_id = await enqueue_pick_list_print_job(
        session,
        ref_type="pick_task",
        ref_id=pick_task_id,
        payload=payload,
    )

    return {
        "pick_task_id": pick_task_id,
        "inserted_lines": inserted_lines,
        "print_job_id": print_job_id,
    }
