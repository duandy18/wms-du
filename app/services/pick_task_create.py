# app/services/pick_task_create.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pick_task import PickTask
from app.models.pick_task_line import PickTaskLine
from app.services.order_service import OrderService
from app.services.pick_task_loaders import load_order_head, load_order_items, load_task

UTC = timezone.utc


async def create_for_order(
    session: AsyncSession,
    *,
    order_id: int,
    warehouse_id: Optional[int] = None,
    source: str = "ORDER",
    priority: int = 100,
) -> PickTask:
    """
    从订单创建拣货任务（订单视角作业入口）：

    ✅ 新合同（作业台）：
    - 由于订单可能尚未分仓，创建拣货任务时必须显式选择仓库（warehouse_id 必填）。
    - 创建成功后会尝试回填 orders.warehouse_id（仅当原来为空时），让后续链路稳定。

    其它行为保持不变：
    - 同步构造/更新软预占：OrderService.reserve
    - 再创建 pick_tasks + pick_task_lines
    """
    order = await load_order_head(session, order_id)
    if not order:
        raise ValueError(f"订单不存在：id={order_id}")

    platform = str(order["platform"]).upper()
    shop_id = str(order["shop_id"])
    ext_no = str(order["ext_order_no"])
    trace_id = order.get("trace_id")

    # ✅ 硬合同：创建拣货任务必须选仓库（因为订单层可能永远不绑定仓库）
    if warehouse_id is None:
        raise ValueError("创建拣货任务失败：请先选择仓库。")

    wh_id = int(warehouse_id)

    # ✅ 尝试回填订单 warehouse_id（仅当为空时）
    await session.execute(
        SA(
            """
            UPDATE orders
               SET warehouse_id = :wid
             WHERE id = :oid
               AND warehouse_id IS NULL
            """
        ),
        {"wid": wh_id, "oid": int(order_id)},
    )

    order_ref = f"ORD:{platform}:{shop_id}:{ext_no}"

    items = await load_order_items(session, order_id)
    if not items:
        raise ValueError("创建拣货任务失败：该订单没有商品行。")

    await OrderService.reserve(
        session=session,
        platform=platform,
        shop_id=shop_id,
        ref=order_ref,
        lines=[{"item_id": r["item_id"], "qty": r["qty"]} for r in items],
        trace_id=trace_id,
    )

    now = datetime.now(UTC)

    task = PickTask(
        warehouse_id=wh_id,
        source=source,
        ref=order_ref,
        priority=priority,
        status="READY",
        assigned_to=None,
        note=None,
        created_at=now,
        updated_at=now,
    )

    session.add(task)
    await session.flush()

    for row in items:
        if row["qty"] <= 0:
            continue
        line = PickTaskLine(
            task_id=task.id,
            order_id=order_id,
            order_line_id=row["order_line_id"],
            item_id=row["item_id"],
            req_qty=row["qty"],
            picked_qty=0,
            batch_code=None,
            prefer_pickface=True,
            target_location_id=None,
            status="OPEN",
            note=None,
            created_at=now,
            updated_at=now,
        )
        session.add(line)

    await session.flush()
    return await load_task(session, task.id)
