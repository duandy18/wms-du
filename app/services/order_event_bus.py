# app/services/order_event_bus.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_writer import AuditEventWriter


class OrderEventBus:
    """
    订单事件总线（轻量版）：

    统一写入 audit_events(flow="ORDER", event="ORDER_*")，保证：
      - flow 固定为 "ORDER"
      - event 使用 ORDER_* 命名
      - meta 至少包含 platform / shop_id / order_id / warehouse_id / lines 等关键信息
      - trace_id 透传

    注意：目前只负责 ORDER 流程，OUTBOUND 等其他 flow 仍由原有调用负责。
    """

    @staticmethod
    async def order_created(
        session: AsyncSession,
        *,
        ref: str,
        platform: str,
        shop_id: str,
        order_id: int,
        order_amount: str,
        pay_amount: str,
        lines: int,
        trace_id: Optional[str] = None,
    ) -> None:
        meta: Dict[str, Any] = {
            "platform": platform.upper(),
            "shop_id": shop_id,
            "order_id": order_id,
            "order_amount": order_amount,
            "pay_amount": pay_amount,
            "lines": lines,
        }
        await AuditEventWriter.write(
            session,
            flow="ORDER",
            event="ORDER_CREATED",
            ref=ref,
            trace_id=trace_id,
            meta=meta,
            auto_commit=False,
        )

    @staticmethod
    async def order_pickable_entered(
        session: AsyncSession,
        *,
        ref: str,
        platform: str,
        shop_id: str,
        order_id: int,
        warehouse_id: int,
        lines: int,
        trace_id: Optional[str] = None,
    ) -> None:
        """
        订单进入“可仓内执行态（pickable）”：
        - 不代表库存已预占/已扣减
        - 只代表可以生成拣货任务、进入仓内作业链路
        """
        meta: Dict[str, Any] = {
            "platform": platform.upper(),
            "shop_id": shop_id,
            "order_id": order_id,
            "warehouse_id": warehouse_id,
            "lines": lines,
        }
        await AuditEventWriter.write(
            session,
            flow="ORDER",
            event="ORDER_PICKABLE_ENTERED",
            ref=ref,
            trace_id=trace_id,
            meta=meta,
            auto_commit=False,
        )

    @staticmethod
    async def order_canceled(
        session: AsyncSession,
        *,
        ref: str,
        platform: str,
        shop_id: str,
        warehouse_id: int,
        status: str,
        trace_id: Optional[str] = None,
    ) -> None:
        meta: Dict[str, Any] = {
            "platform": platform.upper(),
            "shop_id": shop_id,
            "warehouse_id": warehouse_id,
            "status": status,
        }
        await AuditEventWriter.write(
            session,
            flow="ORDER",
            event="ORDER_CANCELED",
            ref=ref,
            trace_id=trace_id,
            meta=meta,
            auto_commit=False,
        )

    @staticmethod
    async def order_shipped(
        session: AsyncSession,
        *,
        ref: str,
        platform: str,
        shop_id: str,
        warehouse_id: int,
        lines: List[Dict[str, int]],
        occurred_at: datetime,
        trace_id: Optional[str] = None,
    ) -> None:
        meta: Dict[str, Any] = {
            "platform": platform.upper(),
            "shop_id": shop_id,
            "warehouse_id": warehouse_id,
            "occurred_at": occurred_at.isoformat(),
            "lines": lines,
        }
        await AuditEventWriter.write(
            session,
            flow="ORDER",
            event="ORDER_SHIPPED",
            ref=ref,
            trace_id=trace_id,
            meta=meta,
            auto_commit=False,
        )

    @staticmethod
    async def order_returned(
        session: AsyncSession,
        *,
        ref: str,
        order_id: int,
        warehouse_id: int,
        lines: List[Dict[str, int]],
        trace_id: Optional[str] = None,
    ) -> None:
        meta: Dict[str, Any] = {
            "order_id": order_id,
            "warehouse_id": warehouse_id,
            "lines": lines,
        }
        await AuditEventWriter.write(
            session,
            flow="ORDER",
            event="ORDER_RETURNED",
            ref=ref,
            trace_id=trace_id,
            meta=meta,
            auto_commit=False,
        )

    @staticmethod
    async def order_delivered(
        session: AsyncSession,
        *,
        ref: str,
        platform: str,
        shop_id: str,
        warehouse_id: int | None = None,
        delivered_at: datetime | None = None,
        trace_id: Optional[str] = None,
    ) -> None:
        """
        订单送达事件（通常由平台签收同步 / 物流轨迹驱动）：

        - flow="ORDER"
        - event="ORDER_DELIVERED"
        - meta 至少包含 platform / shop_id
        - warehouse_id / delivered_at 可选
        """
        meta: Dict[str, Any] = {
            "platform": platform.upper(),
            "shop_id": shop_id,
        }
        if warehouse_id is not None:
            meta["warehouse_id"] = warehouse_id
        if delivered_at is not None:
            meta["delivered_at"] = delivered_at.isoformat()

        await AuditEventWriter.write(
            session,
            flow="ORDER",
            event="ORDER_DELIVERED",
            ref=ref,
            trace_id=trace_id,
            meta=meta,
            auto_commit=False,
        )
