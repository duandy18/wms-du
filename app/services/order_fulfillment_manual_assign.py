# app/services/order_fulfillment_manual_assign.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_writer import AuditEventWriter
from app.services.warehouse_router import OrderContext, OrderLine, StockAvailabilityProvider, WarehouseRouter


@dataclass(frozen=True)
class ManualAssignResult:
    order_id: int
    from_warehouse_id: Optional[int]
    to_warehouse_id: int
    fulfillment_status: str


async def _get_order_id_and_current_actual_wh(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
) -> Tuple[int, Optional[int]]:
    """
    一步到位迁移后：orders 不再包含 warehouse_id 等履约列。
    当前“实际仓”从 order_fulfillment.actual_warehouse_id 读取。
    """
    row = await session.execute(
        text(
            """
            SELECT
              o.id AS order_id,
              f.actual_warehouse_id AS actual_warehouse_id
            FROM orders o
            LEFT JOIN order_fulfillment f ON f.order_id = o.id
            WHERE o.platform = :p
              AND o.shop_id  = :s
              AND o.ext_order_no = :o
            LIMIT 1
            """
        ),
        {"p": platform, "s": shop_id, "o": ext_order_no},
    )
    rec = row.mappings().first()
    if rec is None:
        raise ValueError(f"order not found: platform={platform}, shop_id={shop_id}, ext_order_no={ext_order_no}")

    oid = int(rec["order_id"])
    wid = rec.get("actual_warehouse_id")
    return oid, (int(wid) if wid is not None else None)


async def _load_order_lines_sum(
    session: AsyncSession,
    *,
    order_id: int,
) -> List[Dict[str, Any]]:
    """
    返回整单需求：[{item_id, qty}]
    """
    rows = await session.execute(
        text(
            """
            SELECT item_id, SUM(COALESCE(qty, 0)) AS qty
              FROM order_items
             WHERE order_id = :oid
             GROUP BY item_id
             ORDER BY item_id
            """
        ),
        {"oid": int(order_id)},
    )
    lines: List[Dict[str, Any]] = []
    for item_id, qty in rows.fetchall():
        q = int(qty or 0)
        if q <= 0:
            continue
        lines.append({"item_id": int(item_id), "qty": q})
    return lines


async def _check_can_fulfill_whole_order(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    warehouse_id: int,
    lines: List[Dict[str, Any]],
) -> None:
    """
    Phase 5.1：
    - 人工指定执行仓时，允许做“整单同仓可履约校验”（事实层）
    - 不自动找其他仓，不做 fallback
    """
    if not lines:
        raise ValueError("manual-assign blocked: order has no lines")

    ctx = OrderContext(platform=str(platform), shop_id=str(shop_id), order_id="manual_assign")
    router = WarehouseRouter(availability_provider=StockAvailabilityProvider(session))
    order_lines = [OrderLine(item_id=int(x["item_id"]), qty=int(x["qty"])) for x in lines if int(x["qty"]) > 0]
    r = await router.check_whole_order(ctx=ctx, warehouse_id=int(warehouse_id), lines=order_lines)

    if r.status != "OK":
        insufficient = [x.to_dict() for x in r.insufficient]
        raise ValueError(
            "manual-assign blocked: target warehouse cannot fulfill whole order; "
            f"platform={platform}, shop={shop_id}, wh={warehouse_id}, insufficient={insufficient}"
        )


async def manual_assign_fulfillment_warehouse(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
    order_ref: str,
    trace_id: Optional[str],
    warehouse_id: int,
    reason: str,
    note: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> ManualAssignResult:
    """
    一步到位迁移后（最小事实）：
    - 实际仓写入 order_fulfillment.actual_warehouse_id
    - 计划仓（planned）不在这里改（仍由 Route C/策略写入 planned_warehouse_id）
    - 履约状态写入 order_fulfillment.fulfillment_status

    写入（最小事实）：
      - order_fulfillment.actual_warehouse_id = warehouse_id
      - order_fulfillment.fulfillment_status = 'MANUALLY_ASSIGNED'
      - 清空 blocked_reasons（如果之前是 BLOCKED）
      - 不保留 override_*（审计信息走 AuditEventWriter/event_log）
    审计：
      - OUTBOUND / MANUAL_WAREHOUSE_ASSIGNED
    """
    plat = str(platform or "").upper().strip()
    sid = str(shop_id or "").strip()
    wid = int(warehouse_id)
    if wid <= 0:
        raise ValueError("manual-assign blocked: warehouse_id must be > 0")
    rsn = str(reason or "").strip()
    if not rsn:
        raise ValueError("manual-assign blocked: reason is required")

    order_id, from_wh = await _get_order_id_and_current_actual_wh(
        session, platform=plat, shop_id=sid, ext_order_no=ext_order_no
    )
    lines = await _load_order_lines_sum(session, order_id=order_id)

    # 事实层校验：目标仓必须整单可履约
    await _check_can_fulfill_whole_order(session, platform=plat, shop_id=sid, warehouse_id=wid, lines=lines)

    # 写 order_fulfillment：upsert（最小事实）
    await session.execute(
        text(
            """
            INSERT INTO order_fulfillment(
                order_id,
                planned_warehouse_id,
                actual_warehouse_id,
                fulfillment_status,
                blocked_reasons,
                updated_at
            )
            VALUES (
                :oid,
                NULL,
                :awid,
                'MANUALLY_ASSIGNED',
                NULL,
                now()
            )
            ON CONFLICT (order_id)
            DO UPDATE SET
                actual_warehouse_id = EXCLUDED.actual_warehouse_id,
                fulfillment_status = EXCLUDED.fulfillment_status,
                blocked_reasons = NULL,
                updated_at = now()
            """
        ),
        {
            "oid": int(order_id),
            "awid": int(wid),
        },
    )

    # 审计事件：MANUAL_WAREHOUSE_ASSIGNED
    meta: Dict[str, Any] = {
        "platform": plat,
        "shop": sid,
        "from_warehouse_id": from_wh,
        "to_warehouse_id": int(wid),
        "reason": rsn,
        "operator_id": operator_id,
    }
    if note:
        meta["note"] = str(note).strip()

    try:
        await AuditEventWriter.write(
            session,
            flow="OUTBOUND",
            event="MANUAL_WAREHOUSE_ASSIGNED",
            ref=order_ref,
            trace_id=trace_id,
            meta=meta,
            auto_commit=False,
        )
    except Exception:
        # 审计失败不影响主流程
        pass

    return ManualAssignResult(
        order_id=int(order_id),
        from_warehouse_id=from_wh,
        to_warehouse_id=int(wid),
        fulfillment_status="MANUALLY_ASSIGNED",
    )
