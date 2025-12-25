# app/services/pick_task_create.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

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
    从订单创建拣货任务：

    - 必须先保证订单有 warehouse_id（或调用方显式指定 warehouse_id）；
    - 同步构造/更新软预占：OrderService.reserve → OrderReserveFlow → SoftReserveService；
    - 再创建 pick_tasks + pick_task_lines。
    """
    order = await load_order_head(session, order_id)
    if not order:
        raise ValueError(f"Order not found: id={order_id}")

    platform = str(order["platform"]).upper()
    shop_id = str(order["shop_id"])
    ext_no = str(order["ext_order_no"])
    trace_id = order.get("trace_id")

    order_wh = order.get("warehouse_id")
    if warehouse_id is not None:
        wh_id = int(warehouse_id)
    elif order_wh:
        wh_id = int(order_wh)
    else:
        raise ValueError(
            f"Order {order_id} has no warehouse_id, cannot create pick task or soft reservation. "
            f"请先确保订单绑定仓库（/dev/orders/.../ensure-warehouse 或店铺默认仓绑定）。"
        )

    order_ref = f"ORD:{platform}:{shop_id}:{ext_no}"

    items = await load_order_items(session, order_id)
    if not items:
        raise ValueError(f"Order {order_id} has no items, cannot create pick task.")

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
