# app/services/order_ingest_routing.py
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_writer import AuditEventWriter
from app.services.channel_inventory_service import ChannelInventoryService


async def auto_route_warehouse_if_possible(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    order_id: int,
    order_ref: str,
    trace_id: Optional[str],
    items: Sequence[Mapping[str, Any]],
) -> None:
    """
    完整保留原逻辑：
    - 仅当 items 非空时才尝试
    - 读取 store_warehouse + route_mode
    - STRICT_TOP / FALLBACK
    - 用 ChannelInventoryService.get_available_for_item(raw) 判断是否可 fulfill
    - 命中后写 orders.warehouse_id（仅当为空/0时）
    - 写 WAREHOUSE_ROUTED 审计事件（失败吞掉）
    """
    if not items:
        return

    # 汇总每个 item 的总需求量
    target_qty: Dict[int, int] = {}
    for it in items:
        item_id = it.get("item_id")
        qty = int(it.get("qty") or 0)
        if item_id is None or qty <= 0:
            continue
        iid = int(item_id)
        target_qty[iid] = target_qty.get(iid, 0) + qty

    if not target_qty:
        return

    # 读取店铺绑定的仓 + 路由模式
    rows = await session.execute(
        text(
            """
            SELECT
                sw.warehouse_id,
                COALESCE(sw.is_top, FALSE)                AS is_top,
                COALESCE(sw.priority, 100)                AS priority,
                COALESCE(s.route_mode, 'FALLBACK')        AS route_mode
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

    if not rows_fetched:
        return

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
    considered: List[int] = []

    if candidates_to_try:
        channel_svc = ChannelInventoryService()
        for wid in candidates_to_try:
            considered.append(wid)

            can_fulfill = True
            for item_id, qty in target_qty.items():
                available_raw = await channel_svc.get_available_for_item(
                    session=session,
                    platform=plat_norm,
                    shop_id=shop_id,
                    warehouse_id=wid,
                    item_id=item_id,
                )
                if qty > available_raw:
                    can_fulfill = False
                    break

            if can_fulfill:
                selected_wid = wid
                if route_mode == "STRICT_TOP":
                    selected_reason = "auto_routed_strict_top"
                else:
                    if wid in candidates_top:
                        selected_reason = "auto_routed_top"
                    else:
                        selected_reason = "auto_routed_backup"
                break

    if selected_wid is None:
        return

    # orders 表上写 warehouse_id（仅在原值为空/0 时写入）
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

    # 写 WAREHOUSE_ROUTED 审计事件（供 Trace / Phase4 使用）
    try:
        route_meta = {
            "platform": plat_norm,
            "shop": shop_id,
            "warehouse_id": selected_wid,
            "route_mode": route_mode,
            "reason": selected_reason or "auto_routed",
            "considered": considered,
        }
        await AuditEventWriter.write(
            session,
            flow="OUTBOUND",
            event="WAREHOUSE_ROUTED",
            ref=order_ref,
            trace_id=trace_id,
            meta=route_meta,
            auto_commit=False,
        )
    except Exception:
        pass
