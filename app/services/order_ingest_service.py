# app/services/order_ingest_service.py
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Mapping, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_event_bus import OrderEventBus
from app.services.order_platform_adapters import get_adapter
from app.services.order_utils import to_dec_str

from app.services.order_ingest_items_writer import insert_order_items
from app.services.order_ingest_orders_writer import insert_order_or_get_idempotent
from app.services.order_ingest_routing import auto_route_warehouse_if_possible
from app.services.order_ingest_schema_probe import (
    order_items_has_extras as _order_items_has_extras,
    orders_has_extras as _orders_has_extras,
    orders_has_warehouse_id as _orders_has_warehouse_id,
)


class OrderIngestService:
    """
    订单接入 + 路由选仓（不负责预占 / 取消）。

    提供：
      - ingest_raw(session, platform, shop_id, payload, trace_id)
      - ingest(...)
    """

    @staticmethod
    async def ingest_raw(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        payload: Dict[str, Any],
        trace_id: Optional[str] = None,
    ) -> dict:
        adapter = get_adapter(platform)
        co = adapter.normalize({**payload, "shop_id": shop_id})
        return await OrderIngestService.ingest(
            session,
            platform=co["platform"],
            shop_id=co["shop_id"],
            ext_order_no=co["ext_order_no"],
            occurred_at=co["occurred_at"],
            buyer_name=co.get("buyer_name"),
            buyer_phone=co.get("buyer_phone"),
            order_amount=co.get("order_amount", 0),
            pay_amount=co.get("pay_amount", 0),
            items=co.get("lines", ()),
            address=co.get("address"),
            extras=co.get("extras"),
            trace_id=trace_id,
        )

    @staticmethod
    async def ingest(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        ext_order_no: str,
        occurred_at: Optional[datetime] = None,
        buyer_name: Optional[str] = None,
        buyer_phone: Optional[str] = None,
        order_amount: Decimal | int | float | str = 0,
        pay_amount: Decimal | int | float | str = 0,
        items: Sequence[Mapping[str, Any]] = (),
        address: Optional[Mapping[str, str]] = None,
        extras: Optional[Mapping[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        occurred_at = occurred_at or datetime.now(timezone.utc)
        order_ref = f"ORD:{platform}:{shop_id}:{ext_order_no}"

        # schema probe：保持原行为（每次 ingest 动态检查列是否存在）
        orders_has_extras = await _orders_has_extras(session)
        order_items_has_extras = await _order_items_has_extras(session)
        orders_has_whid = await _orders_has_warehouse_id(session)

        # 1) 写 orders（含幂等处理）
        ins_res = await insert_order_or_get_idempotent(
            session,
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            occurred_at=occurred_at,
            buyer_name=buyer_name,
            buyer_phone=buyer_phone,
            order_amount=order_amount,
            pay_amount=pay_amount,
            items=items,
            extras=extras,
            trace_id=trace_id,
            orders_has_extras=orders_has_extras,
            order_ref=order_ref,
        )
        if ins_res.get("status") == "IDEMPOTENT":
            # 与原实现完全一致：幂等命中直接返回，不写 items/event/routing
            return {
                "status": "IDEMPOTENT",
                "id": ins_res.get("id"),
                "ref": order_ref,
            }

        order_id = int(ins_res["id"])

        # 2) 写 order_items
        await insert_order_items(
            session,
            order_id=order_id,
            items=items,
            order_items_has_extras=order_items_has_extras,
        )

        # 3) 写 ORDER_CREATED（订单事件总线）
        try:
            await OrderEventBus.order_created(
                session,
                ref=order_ref,
                platform=platform,
                shop_id=shop_id,
                order_id=order_id,
                order_amount=to_dec_str(order_amount),
                pay_amount=to_dec_str(pay_amount),
                lines=len(items or ()),
                trace_id=trace_id,
            )
        except Exception:
            pass

        # 4) 路由选仓（orders.warehouse_id + 审计事件）
        if items and orders_has_whid:
            await auto_route_warehouse_if_possible(
                session,
                platform=platform,
                shop_id=shop_id,
                order_id=order_id,
                order_ref=order_ref,
                trace_id=trace_id,
                items=items,
            )

        return {
            "status": "OK",
            "id": order_id,
            "ref": order_ref,
        }
