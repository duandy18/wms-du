# app/services/platform_events_actions.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_service import OrderService
from app.services.outbound_service import OutboundService

from app.services.platform_events_ship import build_ship_lines_for_commit

try:
    from app.models.warehouse import WarehouseCode
except Exception:

    class WarehouseCode:  # type: ignore
        MAIN = "MAIN"


def _build_lines_for_reserve_or_cancel(task: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {"item_id": int(x["item_id"]), "qty": int(x["qty"])}
        for x in (task.get("lines") or [])
        if "item_id" in x and "qty" in x
    ]


async def do_reserve(
    *,
    session: Optional[AsyncSession],
    platform: str,
    task: Dict[str, Any],
    trace_id: str,
) -> int:
    """
    RESERVE：当前语义为 enter_pickable（生成拣货任务/打印队列，不做预占）
    返回 lines 数量（便于 audit 记录）
    """
    if not task.get("ref"):
        raise ValueError("Missing ref for RESERVE")

    lines = _build_lines_for_reserve_or_cancel(task)

    await OrderService.reserve(
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

    lines = _build_lines_for_reserve_or_cancel(task)

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
    SHIP：直接调用 OutboundService.commit 扣库存（库存裁决点）
    返回 lines 数量（便于 audit 记录）
    """
    if not task.get("ref"):
        raise ValueError("Missing ref for SHIP")

    lines = build_ship_lines_for_commit(raw_event=raw_event, mapped=mapped, task=task)

    occurred_at = datetime.now(timezone.utc)
    wh_code = str(
        (mapped.get("warehouse_code") if isinstance(mapped, dict) else None)
        or task.get("warehouse_code")
        or getattr(WarehouseCode, "MAIN", "MAIN")
    )

    svc = OutboundService()
    await svc.commit(
        session=session,
        order_id=task.get("ref"),
        lines=lines,
        occurred_at=occurred_at,
        warehouse_code=wh_code,
        trace_id=trace_id,
    )
    return len(lines)
