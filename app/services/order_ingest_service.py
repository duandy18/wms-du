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
from app.services.order_ingest_lines_writer import insert_order_lines
from app.services.order_ingest_orders_writer import insert_order_or_get_idempotent
from app.services.order_ingest_routing import auto_route_warehouse_if_possible
from app.services.order_ingest_schema_probe import (
    order_items_has_extras as _order_items_has_extras,
    orders_has_extras as _orders_has_extras,
)
from app.services.order_ingest_address_writer import upsert_order_address

_VALID_SCOPES = {"PROD", "DRILL"}


def _norm_scope(scope: Optional[str]) -> str:
    sc = (scope or "").strip().upper() or "PROD"
    if sc not in _VALID_SCOPES:
        raise ValueError("scope must be PROD|DRILL")
    return sc


class OrderIngestService:
    """
    订单接入（ingest）主线 —— Route C（收敛版）

    ✅ 新主线合同（两态）：
      - OK / IDEMPOTENT：订单落库 + 行事实 + 地址快照 + 触发 routing 写入 order_fulfillment（planned/actual）
      - FULFILLMENT_BLOCKED：省份缺失 / 服务仓未配置（显式暴露，等待人工/配置修复）

    ❌ 明确不做：
      - ingest 阶段库存判断
      - ingest 阶段自动 reserve（库存不足由人工改派/退单处理）
      - ingest 阶段探测 orders 是否存在 warehouse_id（routing 自己写 order_fulfillment）
    """

    @staticmethod
    async def ingest_raw(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        payload: Dict[str, Any],
        trace_id: Optional[str] = None,
        scope: str = "PROD",
    ) -> dict:
        adapter = get_adapter(platform)
        co = adapter.normalize({**payload, "shop_id": shop_id})
        return await OrderIngestService.ingest(
            session,
            scope=scope,
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
        scope: str = "PROD",
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
        sc = _norm_scope(scope)
        plat = (platform or "").upper().strip()
        occurred_at = occurred_at or datetime.now(timezone.utc)
        order_ref = f"ORD:{plat}:{shop_id}:{ext_order_no}"

        orders_has_extras = await _orders_has_extras(session)
        order_items_has_extras = await _order_items_has_extras(session)

        # 1) orders（幂等）
        ins_res = await insert_order_or_get_idempotent(
            session,
            scope=sc,
            platform=plat,
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

        idempotent_hit = ins_res.get("status") == "IDEMPOTENT"

        order_id_raw = ins_res.get("id")
        if order_id_raw is None:
            raise RuntimeError("订单接入失败：insert_order_or_get_idempotent 未返回 id")
        order_id = int(order_id_raw)

        # 2) order_items（非幂等才写）
        if not idempotent_hit:
            await insert_order_items(
                session,
                order_id=order_id,
                items=items,
                order_items_has_extras=order_items_has_extras,
            )

            # 3) ORDER_CREATED（非幂等才写）
            try:
                await OrderEventBus.order_created(
                    session,
                    ref=order_ref,
                    platform=plat,
                    shop_id=shop_id,
                    order_id=order_id,
                    order_amount=to_dec_str(order_amount),
                    pay_amount=to_dec_str(pay_amount),
                    lines=len(items or ()),
                    trace_id=trace_id,
                )
            except Exception:
                pass

        # 3.25) order_lines（标准化行事实：解释/作业共用）
        try:
            if items:
                await insert_order_lines(session, order_id=order_id, items=items)
        except Exception:
            pass

        # 3.5) order_address（审计/解释）
        try:
            await upsert_order_address(session, order_id=order_id, address=address)
        except Exception:
            pass

        # 4) Route C：不再探测 orders 是否存在 warehouse_id；routing 直接写 order_fulfillment（planned/actual）或 BLOCKED
        route_payload: Optional[dict] = None
        route_status = "SKIPPED"

        if items:
            rr = await auto_route_warehouse_if_possible(
                session,
                platform=plat,
                shop_id=shop_id,
                order_id=order_id,
                order_ref=order_ref,
                trace_id=trace_id,
                items=items,
                address=address,
            )
            if isinstance(rr, dict):
                route_payload = rr
                route_status = str(rr.get("status") or "CHECKED")

                # ✅ Phase 5：BLOCKED 仍然是可接受结果
                # 但“幂等”描述的是写入行为，因此：
                # - 首次创建命中 BLOCKED => status=FULFILLMENT_BLOCKED
                # - 幂等命中再次 ingest => status=IDEMPOTENT，同时 route 仍然 BLOCKED
                if route_status == "FULFILLMENT_BLOCKED":
                    return {
                        "status": "IDEMPOTENT" if idempotent_hit else "FULFILLMENT_BLOCKED",
                        "id": order_id,
                        "ref": order_ref,
                        "route": route_payload,
                        "ingest_state": "CREATED",
                        "route_status": route_status,
                    }

        # ✅ 新主线：不在 ingest 阶段 reserve
        return {
            "status": "IDEMPOTENT" if idempotent_hit else "OK",
            "id": order_id,
            "ref": order_ref,
            "route": route_payload,
            "ingest_state": "CREATED",
            "route_status": route_status,
        }
