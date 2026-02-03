# app/services/pick_task_create.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pick_task import PickTask
from app.models.pick_task_line import PickTaskLine
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

    ✅ Phase 5.1 合同（严格）：
    - 创建拣货任务时必须显式选择仓库（warehouse_id 必填）。
    - 且该仓库必须与订单已明确的执行仓一致（orders.warehouse_id 必须已存在）。
    - ❌ 禁止任何“隐性回填 orders.warehouse_id”的路径（本函数不写 orders.warehouse_id）。

    ✅ Pick 蓝皮书（主线收敛）：
    - create_for_order 只创建任务 + 行（facts container）。
    - ❌ 不做任何库存/台账/旧链路判断，不触碰 stocks / ledger。
    - 库存是否足够、幂等裁决、台账写入：全部在 Commit 单点完成。
    """
    order = await load_order_head(session, order_id)
    if not order:
        raise ValueError(f"订单不存在：id={order_id}")

    platform = str(order["platform"]).upper()
    shop_id = str(order["shop_id"])
    ext_no = str(order["ext_order_no"])

    # ✅ 硬合同：创建拣货任务必须选仓库
    if warehouse_id is None:
        raise ValueError("创建拣货任务失败：请先选择仓库。")

    wh_id = int(warehouse_id)

    # ✅ Phase 5.1：禁止隐性回填 orders.warehouse_id
    # 这里必须要求订单已经通过“人工指定执行仓”写入了 warehouse_id，
    # 并且与本次创建 pick task 的 warehouse_id 一致。
    cur_wh_raw = order.get("warehouse_id")
    cur_wh = int(cur_wh_raw) if cur_wh_raw not in (None, 0, "0") else None
    fstat = str(order.get("fulfillment_status") or "")

    if cur_wh is None:
        raise ValueError(
            "创建拣货任务失败：订单尚未指定执行仓（warehouse_id 为空）。"
            "请先在订单履约中执行“人工指定执行仓（manual-assign）”。"
        )

    if int(cur_wh) != int(wh_id):
        raise ValueError(
            "创建拣货任务失败：所选仓库与订单执行仓不一致。"
            f" order.warehouse_id={int(cur_wh)} vs selected={int(wh_id)}"
        )

    # （可选但推荐）状态护栏：SERVICE_ASSIGNED 不能直接进入拣货
    if fstat in ("SERVICE_ASSIGNED", "FULFILLMENT_BLOCKED"):
        raise ValueError(
            f"创建拣货任务失败：订单状态不允许拣货：fulfillment_status={fstat}。"
            "请先人工指定执行仓并进入可履约状态。"
        )

    order_ref = f"ORD:{platform}:{shop_id}:{ext_no}"

    items = await load_order_items(session, order_id)
    if not items:
        raise ValueError("创建拣货任务失败：该订单没有商品行。")

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
