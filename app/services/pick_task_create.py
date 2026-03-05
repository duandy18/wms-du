# app/services/pick_task_create.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pick_task import PickTask
from app.models.pick_task_line import PickTaskLine
from app.services.pick_task_loaders import load_order_head, load_order_items, load_task

UTC = timezone.utc


def _norm_int(v: object) -> Optional[int]:
    if v in (None, 0, "0", ""):
        return None
    try:
        n = int(v)  # type: ignore[arg-type]
        return n if n > 0 else None
    except Exception:
        return None


async def _load_fulfillment_brief(session: AsyncSession, *, order_id: int) -> Tuple[Optional[int], Optional[str]]:
    """
    Phase 5+：执行判断只能读 order_fulfillment（authority）。

    返回：
    - actual_warehouse_id（执行仓事实）
    - fulfillment_status（用于 BLOCKED gate 等）
    """
    row = (
        await session.execute(
            text(
                """
                SELECT actual_warehouse_id, fulfillment_status
                  FROM order_fulfillment
                 WHERE order_id = :oid
                 LIMIT 1
                """
            ),
            {"oid": int(order_id)},
        )
    ).first()
    if not row:
        return None, None
    actual_wh = int(row[0]) if row[0] is not None else None
    fstat = str(row[1]) if row[1] is not None else None
    return actual_wh, fstat


async def _find_existing_task_id(
    session: AsyncSession,
    *,
    ref: str,
    warehouse_id: int,
) -> Optional[int]:
    """
    幂等护栏：同一 (ref, warehouse_id) 只能存在一个 pick_task。
    若已存在则返回其 id。
    """
    row = (
        await session.execute(
            select(PickTask.id).where(
                PickTask.ref == str(ref),
                PickTask.warehouse_id == int(warehouse_id),
            )
        )
    ).first()
    if not row:
        return None
    return int(row[0])


def _aggregate_order_items_by_item(
    items: list[dict],
) -> Dict[int, Tuple[int, Optional[int]]]:
    """
    模型层收敛（药房处方语义）：
    - 强制“一 item 一行”
    - 将订单明细按 item_id 聚合 qty
    - 同一 item_id 若存在多个 order_line_id：取最小的作为代表（用于可追溯/兼容字段）
      注意：这个代表 id 只用于挂接，不表达“拆行”语义。
    返回：
      { item_id: (qty_sum, representative_order_line_id) }
    """
    agg: Dict[int, Tuple[int, Optional[int]]] = {}

    for row in items:
        item_id = int(row.get("item_id") or 0)
        if item_id <= 0:
            continue

        qty = int(row.get("qty") or 0)
        if qty <= 0:
            continue

        ol = row.get("order_line_id")
        order_line_id = int(ol) if ol is not None else None

        if item_id not in agg:
            agg[item_id] = (qty, order_line_id)
        else:
            cur_qty, cur_ol = agg[item_id]
            new_qty = cur_qty + qty

            # 代表 order_line_id：取更小的那个（保持稳定）
            rep = cur_ol
            if rep is None:
                rep = order_line_id
            elif order_line_id is not None and int(order_line_id) < int(rep):
                rep = order_line_id

            agg[item_id] = (new_qty, rep)

    return agg


async def create_for_order(
    session: AsyncSession,
    *,
    order_id: int,
    warehouse_id: Optional[int] = None,
    source: str = "ORDER",
    priority: int = 100,
) -> PickTask:
    """
    从订单创建拣货任务（订单视角作业入口）。

    ✅ Phase 5+（执行域收口版）：
    - 执行仓必须来自 order_fulfillment.actual_warehouse_id（authority）
    - ❌ 不再允许通过「platform/shop_id → 店铺默认仓」推断执行仓（影子语义）
    - 若调用方显式传 warehouse_id：仅用于校验/对齐（不得绕过 authority）
      - 若 fulfillment.actual_warehouse_id 存在且与传入不一致 → 拒绝
      - 若 fulfillment.actual_warehouse_id 为空 → 拒绝（应先走 reserve/manual-assign 明确执行仓锚点）

    ✅ 状态护栏：
    - 只拦真正的 FULFILLMENT_BLOCKED（避免误伤空值/未设置）

    ✅ 幂等：
    - 若同一 (ref, warehouse_id) 已存在 pick_task，直接返回已存在的任务（不重复插入）

    ✅ 模型层收敛（药房处方语义）：
    - 强制“一 item 一行”（PickTaskLine 粒度 = item_id）
    - 即使订单明细里同一 item 拆成多行，这里也会聚合为一行 req_qty
    """
    order = await load_order_head(session, order_id)
    if not order:
        raise ValueError(f"订单不存在：id={order_id}")

    platform = str(order.get("platform") or "").upper()
    shop_id = str(order.get("shop_id") or "")
    ext_no = str(order.get("ext_order_no") or "")

    # 1) authority：执行仓与履约状态只读 order_fulfillment
    actual_wh, fstat = await _load_fulfillment_brief(session, order_id=int(order_id))

    # 2) 状态护栏：只拦 BLOCKED
    if (fstat or "").strip().upper() == "FULFILLMENT_BLOCKED":
        raise ValueError(
            f"创建拣货任务失败：订单履约被阻断：fulfillment_status={fstat}。"
            "请先完成履约策略处理/改派，使订单进入可执行状态。"
        )

    # 3) warehouse_id 收口：必须以 actual 为准
    requested_wh = _norm_int(warehouse_id)
    if requested_wh is not None:
        if actual_wh is None:
            raise ValueError(
                "创建拣货任务失败：订单尚未绑定执行仓（order_fulfillment.actual_warehouse_id 为空），"
                "禁止通过入参 warehouse_id 绕过执行域 authority。"
                f" platform={platform}, shop_id={shop_id}, order_id={order_id}"
            )
        if int(actual_wh) != int(requested_wh):
            raise ValueError(
                "创建拣货任务失败：执行仓冲突（以 order_fulfillment.actual_warehouse_id 为准）。"
                f" existing_actual_warehouse_id={actual_wh}, incoming_warehouse_id={requested_wh}, order_id={order_id}"
            )
        wh_id = int(actual_wh)
    else:
        if actual_wh is None:
            raise ValueError(
                "创建拣货任务失败：订单尚未绑定执行仓（order_fulfillment.actual_warehouse_id 为空）。"
                "请先走 reserve/assign 明确执行仓锚点后再创建拣货任务。"
                f" platform={platform}, shop_id={shop_id}, order_id={order_id}"
            )
        wh_id = int(actual_wh)

    # 4) ref：订单维度幂等锚点
    order_ref = f"ORD:{platform}:{shop_id}:{ext_no}"

    # ✅ 幂等：若已存在 (ref, warehouse_id) 则直接返回
    existing_id = await _find_existing_task_id(session, ref=order_ref, warehouse_id=int(wh_id))
    if existing_id is not None:
        return await load_task(session, existing_id)

    # 5) 加载订单明细，并做“一 item 一行”聚合
    raw_items = await load_order_items(session, order_id)
    if not raw_items:
        raise ValueError("创建拣货任务失败：该订单没有商品行。")

    agg = _aggregate_order_items_by_item(raw_items)
    if not agg:
        raise ValueError("创建拣货任务失败：该订单没有有效商品行（qty<=0 或 item_id 缺失）。")

    now = datetime.now(UTC)

    task = PickTask(
        warehouse_id=int(wh_id),
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

    # 并发兜底
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing_id2 = await _find_existing_task_id(session, ref=order_ref, warehouse_id=int(wh_id))
        if existing_id2 is None:
            raise
        return await load_task(session, existing_id2)

    # 6) 生成 PickTaskLine：一 item 一行
    for item_id, (qty_sum, rep_order_line_id) in agg.items():
        if qty_sum <= 0:
            continue
        line = PickTaskLine(
            task_id=task.id,
            order_id=order_id,
            order_line_id=rep_order_line_id,
            item_id=int(item_id),
            req_qty=int(qty_sum),
            picked_qty=0,
            batch_code=None,
            prefer_pickface=True,
            status="OPEN",
            note=None,
            created_at=now,
            updated_at=now,
        )
        session.add(line)

    await session.flush()
    return await load_task(session, task.id)
