# app/services/order_ingest_service.py
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Mapping, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_writer import AuditEventWriter
from app.services.order_event_bus import OrderEventBus
from app.services.order_platform_adapters import get_adapter
from app.services.order_reserve_flow_reserve import reserve_flow
from app.services.order_utils import to_dec_str

from app.services.order_ingest_items_writer import insert_order_items
from app.services.order_ingest_orders_writer import insert_order_or_get_idempotent
from app.services.order_ingest_routing import auto_route_warehouse_if_possible
from app.services.order_ingest_schema_probe import (
    order_items_has_extras as _order_items_has_extras,
    orders_has_extras as _orders_has_extras,
    orders_has_warehouse_id as _orders_has_warehouse_id,
)
from app.services.order_ingest_address_writer import upsert_order_address


class OrderIngestService:
    """
    订单接入（ingest）主线 —— 路线 C（执行期约束满足式履约）

    主线合同（两态）：
      - OK + RESERVED：可履约事实（订单即库存事实闭环成立）
      - FULFILLMENT_BLOCKED：不可履约事实（必须显式暴露，不进入 reserve）
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
        # 关键修复：平台一律大写，保证 ref 合同与 orders.platform 口径一致
        plat = (platform or "").upper().strip()
        occurred_at = occurred_at or datetime.now(timezone.utc)
        order_ref = f"ORD:{plat}:{shop_id}:{ext_order_no}"

        # schema probe：保持原行为（每次 ingest 动态检查列是否存在）
        orders_has_extras = await _orders_has_extras(session)
        order_items_has_extras = await _order_items_has_extras(session)
        orders_has_whid = await _orders_has_warehouse_id(session)

        # 1) 写 orders（含幂等处理）
        ins_res = await insert_order_or_get_idempotent(
            session,
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

        # 幂等命中：不重复写 items / ORDER_CREATED，但允许补齐 route/reserve（防止僵尸订单）。
        idempotent_hit = ins_res.get("status") == "IDEMPOTENT"

        order_id_raw = ins_res.get("id")
        if order_id_raw is None:
            raise RuntimeError("订单接入失败：insert_order_or_get_idempotent 未返回 id")
        order_id = int(order_id_raw)

        # 2) 写 order_items（仅在非幂等时执行）
        if not idempotent_hit:
            await insert_order_items(
                session,
                order_id=order_id,
                items=items,
                order_items_has_extras=order_items_has_extras,
            )

            # 3) 写 ORDER_CREATED（订单事件总线）——也只在非幂等时执行
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

        # ✅ 3.5) 写 order_address 快照（审计/解释用）
        # - 不影响路由主线
        # - 幂等命中时也允许补齐 address（防止历史订单缺地址）
        try:
            await upsert_order_address(session, order_id=order_id, address=address)
        except Exception:
            # 地址写入失败不应阻断主线（避免因历史字段差异导致 ingest 失败）
            pass

        # 4) 履约校验（路线 C）：命中服务仓 + 校验整单履约
        #    失败必须显式暴露，且不进入 reserve。
        route_payload: Optional[dict] = None
        route_status = "SKIPPED"

        if items and orders_has_whid:
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

                if route_status == "FULFILLMENT_BLOCKED":
                    return {
                        "status": "FULFILLMENT_BLOCKED",
                        "id": order_id,
                        "ref": order_ref,
                        "route": route_payload,
                    }

        # 5) 立即 reserve（仅当 route 未阻断）
        if items and orders_has_whid:
            lines = []
            for it in items or ():
                item_id = it.get("item_id")
                qty = int(it.get("qty") or 0)
                if item_id is None or qty <= 0:
                    continue
                lines.append({"item_id": int(item_id), "qty": int(qty)})

            try:
                await reserve_flow(
                    session,
                    platform=plat,
                    shop_id=shop_id,
                    ref=order_ref,
                    lines=lines,
                    trace_id=trace_id,
                )
            except Exception as e:
                try:
                    await AuditEventWriter.write(
                        session,
                        event="ORDER_RESERVE_FAILED",
                        ref=order_ref,
                        trace_id=trace_id,
                        data={
                            "order_id": order_id,
                            "error": str(e),
                            "route_status": route_status,
                            "route": route_payload,
                        },
                    )
                except Exception:
                    pass

                return {
                    "status": "RESERVE_FAILED",
                    "id": order_id,
                    "ref": order_ref,
                    "route": route_payload,
                    "error": str(e),
                }

        return {
            # ✅ 幂等命中必须显式返回 IDEMPOTENT（测试/合同依赖）
            "status": "IDEMPOTENT" if idempotent_hit else "OK",
            "id": order_id,
            "ref": order_ref,
            "route": route_payload,
            "ingest_state": "RESERVED" if (items and orders_has_whid) else "CREATED",
        }
