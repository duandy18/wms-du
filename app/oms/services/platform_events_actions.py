# app/oms/services/platform_events_actions.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.oms.services.order_service import OrderService


def _build_lines_for_pick_or_cancel(task: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {"item_id": int(x["item_id"]), "qty": int(x["qty"])}
        for x in (task.get("lines") or [])
        if "item_id" in x and "qty" in x
    ]


async def do_pick(
    *,
    session: Optional[AsyncSession],
    platform: str,
    task: Dict[str, Any],
    trace_id: str,
) -> int:
    """
    PICK：进入拣货主线（生成拣货任务/打印队列，不做预占）
    返回 lines 数量（便于 audit 记录）
    """
    if not task.get("ref"):
        raise ValueError("Missing ref for PICK")

    lines = _build_lines_for_pick_or_cancel(task)

    await OrderService.enter_pickable(
        session,
        platform=platform,
        shop_id=task.get("shop_id"),
        ref=task.get("ref"),
        lines=lines,
        trace_id=trace_id,
    )
    return len(lines)


async def do_cancel(
    *,
    session: Optional[AsyncSession],
    platform: str,
    task: Dict[str, Any],
    trace_id: str,
) -> int:
    """
    CANCEL：取消订单执行态，不做预占释放
    返回 lines 数量（便于 audit 记录）
    """
    if not task.get("ref"):
        raise ValueError("Missing ref for CANCEL")

    lines = _build_lines_for_pick_or_cancel(task)

    await OrderService.cancel(
        session,
        platform=platform,
        shop_id=task.get("shop_id"),
        ref=task.get("ref"),
        lines=lines,
        trace_id=trace_id,
    )
    return len(lines)


async def do_ship(
    *,
    session: Optional[AsyncSession],
    platform: str,
    raw_event: Dict[str, Any],
    mapped: Any,
    task: Dict[str, Any],
    trace_id: str,
) -> int:
    """
    SHIP：平台事件不再自动扣 WMS 库存。

    终态执行入口是正式 WMS 出库提交链路：
    - /wms/outbound/orders/{order_id}/submit
    - /wms/outbound/manual/{doc_id}/submit

    平台事件中的 batch_code / lot_code 不能作为库存结构事实。
    """
    _ = session, platform, raw_event, mapped, trace_id

    if not task.get("ref"):
        raise ValueError("Missing ref for SHIP")

    raise ValueError(
        "platform_ship_stock_commit_retired: use formal WMS outbound submit with lot_id"
    )
