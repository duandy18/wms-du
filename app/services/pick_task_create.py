# app/services/pick_task_create.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pick_task import PickTask
from app.models.pick_task_line import PickTaskLine
from app.services.pick_task_loaders import load_order_head, load_order_items, load_task
from app.services.store_service import StoreService

UTC = timezone.utc


def _norm_int(v: object) -> Optional[int]:
    if v in (None, 0, "0", ""):
        return None
    try:
        n = int(v)  # type: ignore[arg-type]
        return n if n > 0 else None
    except Exception:
        return None


async def _resolve_execution_warehouse_for_order(session: AsyncSession, *, order: dict) -> Optional[int]:
    """
    Phase 2（收敛版）：执行仓只通过「订单→店铺」解析，不消费订单上的仓字段。

    ✅ 核心原则：
    - 订单只提供 platform / shop_id（店铺事实）
    - 执行仓只能通过店铺绑定（store default）解析，避免订单维度仓字段造成事实漂移
    - ❌ 不使用 fulfillment_warehouse_id（避免与店铺默认仓冲突）
    - ❌ 不使用 orders.warehouse_id / orders.service_warehouse_id（不从订单字段解析仓）

    返回：
    - 解析成功：warehouse_id
    - 解析失败：None（由上层抛出可读错误）
    """
    plat = str(order.get("platform") or "").upper().strip()
    shop = str(order.get("shop_id") or "").strip()
    if not plat or not shop:
        return None

    wid2 = await StoreService.resolve_default_warehouse_for_platform_shop(session, platform=plat, shop_id=shop)
    return _norm_int(wid2)


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
    从订单创建拣货任务（订单视角作业入口）：

    ✅ Phase 2 合同（收敛版）：
    - 自动入口：不传 warehouse_id → 仅通过「platform/shop_id → 店铺默认仓」解析执行仓
    - 手工入口（兼容）：若调用方显式传 warehouse_id → 直接使用该仓（用于 manual-from-order）
    - ❌ 不消费订单上的 warehouse_id / service_warehouse_id / fulfillment_warehouse_id 来解析执行仓
    - ❌ 不隐性回填 orders.warehouse_id（本函数不写 orders 表）

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

    # 1) 若调用方显式传 warehouse_id（手工入口），优先使用
    requested_wh = _norm_int(warehouse_id)

    # 2) 否则：自动解析执行仓（仅通过店铺默认仓）
    wh_id = requested_wh
    if wh_id is None:
        try:
            wh_id = await _resolve_execution_warehouse_for_order(session, order=order)
        except Exception as e:
            raise ValueError(
                "创建拣货任务失败：无法通过店铺绑定解析默认执行仓。"
                f" platform={platform}, shop_id={shop_id}, err={str(e)}"
            )

    if wh_id is None:
        raise ValueError(
            "创建拣货任务失败：无法解析执行仓（warehouse_id）。"
            f"请先在店铺管理中完成仓库绑定并设置默认仓。platform={platform}, shop_id={shop_id}"
        )

    # 3) 状态护栏：只拦真正的 BLOCKED（不要误伤空值/未设置）
    fstat = str(order.get("fulfillment_status") or "")
    if fstat == "FULFILLMENT_BLOCKED":
        raise ValueError(
            f"创建拣货任务失败：订单状态不允许拣货：fulfillment_status={fstat}。"
            "请先完成履约策略处理，使订单进入可拣货状态。"
        )

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

    # 并发兜底：极端情况下两个请求同时通过“未存在”检查，
    # flush 时会命中 uq_pick_tasks_ref_wh；此时回滚并返回已存在的那条。
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
            order_line_id=rep_order_line_id,  # 代表 order_line_id（仅用于追溯/兼容）
            item_id=int(item_id),
            req_qty=int(qty_sum),
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
