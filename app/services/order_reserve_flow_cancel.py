# app/services/order_reserve_flow_cancel.py
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_writer import AuditEventWriter
from app.services.order_event_bus import OrderEventBus
from app.services.order_trace_helper import set_order_status_by_ref

from app.services.order_reserve_flow_reserve import resolve_warehouse_for_order


async def cancel_flow(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ref: str,
    lines: Sequence[Mapping[str, Any]],
    trace_id: Optional[str] = None,
) -> dict:
    """
    ✅ 取消订单执行流（当前主线语义）

    - 不触碰库存/台账
    - 取消仅表达“订单不再进入后续执行链路”，属于订单状态与审计层动作
    """
    platform_db = platform.upper()

    warehouse_id = await resolve_warehouse_for_order(
        session,
        platform=platform_db,
        shop_id=shop_id,
        ref=ref,
    )

    status = "CANCELED"

    # 尽力设置订单状态（不阻塞主线）
    try:
        await set_order_status_by_ref(
            session,
            platform=platform_db,
            shop_id=shop_id,
            ref=ref,
            new_status="CANCELED",
        )
    except Exception:
        pass

    # 写审计（ORDER 事件 + OUTBOUND 侧事件）
    try:
        await OrderEventBus.order_canceled(
            session,
            ref=ref,
            platform=platform_db,
            shop_id=shop_id,
            warehouse_id=warehouse_id,
            status=status,
            trace_id=trace_id,
        )

        await AuditEventWriter.write(
            session,
            flow="OUTBOUND",
            event="ORDER_CANCELED",
            ref=ref,
            trace_id=trace_id,
            meta={
                "platform": platform_db,
                "shop": shop_id,
                "warehouse_id": warehouse_id,
                "status": status,
                "lines": len(lines or ()),
            },
            auto_commit=False,
        )
    except Exception:
        pass

    return {
        "status": status,
        "ref": ref,
    }
