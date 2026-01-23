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


async def _get_order_id_and_current_wh(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
) -> Tuple[int, Optional[int]]:
    row = await session.execute(
        text(
            """
            SELECT id, warehouse_id
              FROM orders
             WHERE platform = :p
               AND shop_id  = :s
               AND ext_order_no = :o
             LIMIT 1
            """
        ),
        {"p": platform, "s": shop_id, "o": ext_order_no},
    )
    rec = row.first()
    if rec is None:
        raise ValueError(f"order not found: platform={platform}, shop_id={shop_id}, ext_order_no={ext_order_no}")
    oid = int(rec[0])
    wid = rec[1]
    return oid, (int(wid) if wid else None)


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
    Phase 5.1：人工指定执行仓（唯一允许写 orders.warehouse_id 的主线入口）

    写入：
      - orders.warehouse_id = warehouse_id
      - orders.fulfillment_warehouse_id = warehouse_id
      - orders.fulfillment_status = 'MANUALLY_ASSIGNED'
      - 清空 blocked 字段（如果之前是 BLOCKED）
      - 兼容字段：overridden_by / overridden_at / override_reason（若表存在则写，不强依赖）
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

    order_id, from_wh = await _get_order_id_and_current_wh(session, platform=plat, shop_id=sid, ext_order_no=ext_order_no)
    lines = await _load_order_lines_sum(session, order_id=order_id)

    # 事实层校验：目标仓必须整单可履约
    await _check_can_fulfill_whole_order(session, platform=plat, shop_id=sid, warehouse_id=wid, lines=lines)

    # 写 orders：只在这里写 warehouse_id（强约束）
    await session.execute(
        text(
            """
            UPDATE orders
               SET warehouse_id = :wid,
                   fulfillment_warehouse_id = :wid,
                   fulfillment_status = 'MANUALLY_ASSIGNED',
                   blocked_reasons = NULL,
                   blocked_detail = NULL,
                   overridden_by = :by,
                   overridden_at = now(),
                   override_reason = :reason
             WHERE id = :oid
            """
        ),
        {
            "wid": int(wid),
            "by": int(operator_id) if operator_id is not None else None,
            "reason": rsn,
            "oid": int(order_id),
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
