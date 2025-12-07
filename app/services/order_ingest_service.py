# app/services/order_ingest_service.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Mapping, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_writer import AuditEventWriter
from app.services.channel_inventory_service import ChannelInventoryService
from app.services.order_event_bus import OrderEventBus
from app.services.order_platform_adapters import get_adapter
from app.services.order_utils import to_dec_str


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

        # 检查 orders / order_items 表是否有 extras 列
        orders_has_extras = bool(
            (
                await session.execute(
                    text(
                        """
                        SELECT 1
                          FROM information_schema.columns
                         WHERE table_schema='public'
                           AND table_name='orders'
                           AND column_name='extras'
                        """
                    )
                )
            ).first()
        )
        order_items_has_extras = bool(
            (
                await session.execute(
                    text(
                        """
                        SELECT 1
                          FROM information_schema.columns
                         WHERE table_schema='public'
                           AND table_name='order_items'
                           AND column_name='extras'
                        """
                    )
                )
            ).first()
        )
        # 是否存在 orders.warehouse_id 列（只有存在时才写仓）
        orders_has_whid = bool(
            (
                await session.execute(
                    text(
                        """
                        SELECT 1
                          FROM information_schema.columns
                         WHERE table_schema='public'
                           AND table_name='orders'
                           AND column_name='warehouse_id'
                        """
                    )
                )
            ).first()
        )

        # ------------------ 写 orders ------------------
        if orders_has_extras:
            sql_ins_orders = text(
                """
                INSERT INTO orders (
                    platform,
                    shop_id,
                    ext_order_no,
                    status,
                    buyer_name,
                    buyer_phone,
                    order_amount,
                    pay_amount,
                    created_at,
                    updated_at,
                    extras,
                    trace_id
                )
                VALUES (
                    :p, :s, :o,
                    'CREATED',
                    :bn, :bp,
                    :oa, :pa,
                    :at, :at,
                    :ex,
                    :tid
                )
                ON CONFLICT ON CONSTRAINT uq_orders_platform_shop_ext DO NOTHING
                RETURNING id
                """
            )
            bind_orders = {
                "p": platform,
                "s": shop_id,
                "o": ext_order_no,
                "bn": buyer_name,
                "bp": buyer_phone,
                "oa": to_dec_str(order_amount),
                "pa": to_dec_str(pay_amount),
                "at": occurred_at,
                "ex": json.dumps(extras or {}, ensure_ascii=False),
                "tid": trace_id,
            }
        else:
            sql_ins_orders = text(
                """
                INSERT INTO orders (
                    platform,
                    shop_id,
                    ext_order_no,
                    status,
                    buyer_name,
                    buyer_phone,
                    order_amount,
                    pay_amount,
                    created_at,
                    updated_at,
                    trace_id
                )
                VALUES (
                    :p, :s, :o,
                    'CREATED',
                    :bn, :bp,
                    :oa, :pa,
                    :at, :at,
                    :tid
                )
                ON CONFLICT ON CONSTRAINT uq_orders_platform_shop_ext DO NOTHING
                RETURNING id
                """
            )
            bind_orders = {
                "p": platform,
                "s": shop_id,
                "o": ext_order_no,
                "bn": buyer_name,
                "bp": buyer_phone,
                "oa": to_dec_str(order_amount),
                "pa": to_dec_str(pay_amount),
                "at": occurred_at,
                "tid": trace_id,
            }

        rec = await session.execute(sql_ins_orders, bind_orders)
        new_id = rec.scalar()
        if new_id is None:
            # 已有同键订单：查 id 并为旧数据补 trace_id（仅在 trace_id 为空时填充）
            row = (
                await session.execute(
                    text(
                        """
                        SELECT id
                          FROM orders
                         WHERE platform=:p
                           AND shop_id=:s
                           AND ext_order_no=:o
                         LIMIT 1
                        """
                    ),
                    {"p": platform, "s": shop_id, "o": ext_order_no},
                )
            ).first()
            order_id = int(row[0]) if row else None
            if order_id is not None and trace_id:
                await session.execute(
                    text(
                        """
                        UPDATE orders
                           SET trace_id = COALESCE(trace_id, :tid)
                         WHERE id = :oid
                        """
                    ),
                    {"oid": order_id, "tid": trace_id},
                )

            return {
                "status": "IDEMPOTENT",
                "id": order_id,
                "ref": order_ref,
            }

        order_id = int(new_id)

        # ------------------ 写 order_items ------------------
        if items:
            if order_items_has_extras:
                sql_item = text(
                    """
                    INSERT INTO order_items (
                        order_id,
                        item_id,
                        sku_id,
                        title,
                        qty,
                        price,
                        discount,
                        amount,
                        shipped_qty,
                        returned_qty,
                        extras
                    )
                    VALUES (
                        :oid, :item_id, :sku_id, :title,
                        :qty, :price, :disc, :amt,
                        :shipped_qty, :returned_qty,
                        CAST(:ex AS jsonb)
                    )
                    ON CONFLICT ON CONSTRAINT uq_order_items_ord_sku DO NOTHING
                    """
                )
            else:
                sql_item = text(
                    """
                    INSERT INTO order_items (
                        order_id,
                        item_id,
                        sku_id,
                        title,
                        qty,
                        price,
                        discount,
                        amount,
                        shipped_qty,
                        returned_qty
                    )
                    VALUES (
                        :oid, :item_id, :sku_id, :title,
                        :qty, :price, :disc, :amt,
                        :shipped_qty, :returned_qty
                    )
                    ON CONFLICT ON CONSTRAINT uq_order_items_ord_sku DO NOTHING
                    """
                )
            for it in items:
                params = {
                    "oid": order_id,
                    "item_id": it.get("item_id"),
                    "sku_id": (it.get("sku_id") or "")[:128],
                    "title": (it.get("title") or "")[:255],
                    "qty": int(it.get("qty") or 0),
                    "price": to_dec_str(it.get("price")),
                    "disc": to_dec_str(it.get("discount")),
                    "amt": to_dec_str(it.get("amount")),
                    "shipped_qty": 0,
                    "returned_qty": 0,
                }
                if order_items_has_extras:
                    params["ex"] = json.dumps(it.get("extras") or {}, ensure_ascii=False)
                await session.execute(sql_item, params)

        # ------------------ 写 ORDER_CREATED（订单事件总线） ------------------
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
            # 不让审计事件影响主流程
            pass

        # ------------------ 路由选仓（orders.warehouse_id） ------------------
        if items and orders_has_whid:
            # 汇总每个 item 的总需求量
            target_qty: Dict[int, int] = {}
            for it in items:
                item_id = it.get("item_id")
                qty = int(it.get("qty") or 0)
                if item_id is None or qty <= 0:
                    continue
                iid = int(item_id)
                target_qty[iid] = target_qty.get(iid, 0) + qty

            if target_qty:
                rows = await session.execute(
                    text(
                        """
                        SELECT
                            sw.warehouse_id,
                            COALESCE(sw.is_top, FALSE)    AS is_top,
                            COALESCE(sw.priority, 100)    AS priority,
                            COALESCE(s.route_mode, 'FALLBACK') AS route_mode
                          FROM store_warehouse AS sw
                          JOIN stores AS s
                            ON sw.store_id = s.id
                         WHERE s.platform = :p
                           AND s.shop_id  = :s
                           AND s.active   = TRUE
                         ORDER BY sw.is_top DESC,
                                  sw.priority ASC,
                                  sw.warehouse_id ASC
                        """
                    ),
                    {"p": platform.upper(), "s": shop_id},
                )
                rows_fetched = rows.fetchall()

                if rows_fetched:
                    candidates_top: List[int] = []
                    candidates_backup: List[int] = []
                    route_mode_raw: Optional[str] = None

                    for wid, is_top, pri, rm in rows_fetched:
                        if route_mode_raw is None:
                            route_mode_raw = rm
                        wid_int = int(wid)
                        if is_top:
                            candidates_top.append(wid_int)
                        else:
                            candidates_backup.append(wid_int)

                    route_mode = (route_mode_raw or "FALLBACK").upper()
                    plat_norm = platform.upper()
                    if route_mode == "STRICT_TOP":
                        candidates_to_try = candidates_top
                    else:
                        candidates_to_try = candidates_top + candidates_backup

                    selected_wid: Optional[int] = None
                    selected_reason: Optional[str] = None

                    if candidates_to_try:
                        channel_svc = ChannelInventoryService()
                        for wid in candidates_to_try:
                            can_fulfill = True
                            for item_id, qty in target_qty.items():
                                available_raw = await channel_svc.get_available_for_item(
                                    session=session,
                                    platform=plat_norm,
                                    shop_id=shop_id,
                                    warehouse_id=wid,
                                    item_id=item_id,
                                )
                                incr = qty
                                if incr > available_raw:
                                    can_fulfill = False
                                    break

                            if can_fulfill:
                                selected_wid = wid
                                if route_mode == "STRICT_TOP":
                                    selected_reason = "strict_top_primary"
                                else:
                                    if wid in candidates_top:
                                        selected_reason = "fallback_primary"
                                    else:
                                        selected_reason = "fallback_backup"
                                break

                    if selected_wid is not None:
                        await session.execute(
                            text(
                                """
                                UPDATE orders
                                   SET warehouse_id = :wid
                                 WHERE id = :oid
                                   AND (warehouse_id IS NULL OR warehouse_id = 0)
                                """
                            ),
                            {"wid": selected_wid, "oid": order_id},
                        )
                        try:
                            route_meta = {
                                "platform": plat_norm,
                                "shop": shop_id,
                                "warehouse_id": selected_wid,
                                "route_mode": route_mode,
                                "reason": selected_reason,
                            }
                            # 🚫 不再使用 flow="OUTBOUND"，避免 lifecycle 误判为出库节点
                            await AuditEventWriter.write(
                                session,
                                flow="ORDER",
                                event="WAREHOUSE_ROUTED",
                                ref=order_ref,
                                trace_id=trace_id,
                                meta=route_meta,
                                auto_commit=False,
                            )
                        except Exception:
                            pass

        return {
            "status": "OK",
            "id": order_id,
            "ref": order_ref,
        }
