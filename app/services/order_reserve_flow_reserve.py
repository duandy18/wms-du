# app/services/order_reserve_flow_reserve.py
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_writer import AuditEventWriter
from app.services.order_event_bus import OrderEventBus
from app.services.order_trace_helper import set_order_status_by_ref
from app.services.order_utils import to_int_pos
from app.services.order_reserve_flow_types import extract_ext_order_no

from app.services.pick_task_auto import resolve_order_and_ensure_task_and_print


async def resolve_warehouse_for_order(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ref: str,
) -> int:
    plat = platform.upper()
    ext_order_no = extract_ext_order_no(plat, shop_id, ref)
    if not ext_order_no:
        raise ValueError(
            f"cannot resolve warehouse for order: invalid ref={ref!r}, "
            f"expected 'ORD:{plat}:{shop_id}:{{ext_order_no}}'"
        )

    row = await session.execute(
        text(
            """
            SELECT
              f.actual_warehouse_id AS warehouse_id,
              f.fulfillment_status AS fulfillment_status,
              f.blocked_reasons AS blocked_reasons
            FROM orders o
            LEFT JOIN order_fulfillment f ON f.order_id = o.id
            WHERE o.platform = :p
              AND o.shop_id  = :s
              AND o.ext_order_no = :o
            LIMIT 1
            """
        ),
        {"p": plat, "s": shop_id, "o": ext_order_no},
    )
    rec = row.first()
    if rec is None:
        raise ValueError(
            f"cannot resolve warehouse for order: order not found "
            f"platform={plat}, shop={shop_id}, ext_order_no={ext_order_no}"
        )

    warehouse_id = rec[0]
    fulfillment_status = rec[1]
    blocked_reasons = rec[2]

    if warehouse_id is None or int(warehouse_id) == 0:
        extra = []
        if fulfillment_status:
            extra.append(f"fulfillment_status={fulfillment_status}")
        if blocked_reasons:
            extra.append(f"blocked_reasons={blocked_reasons}")
        suffix = ("; " + ", ".join(extra)) if extra else ""
        raise ValueError(
            f"cannot resolve warehouse for order: "
            f"platform={plat}, shop={shop_id}, ext_order_no={ext_order_no}, "
            f"warehouse_id is NULL/0{suffix}"
        )

    return int(warehouse_id)


async def _resolve_order_id_and_trace_id(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
) -> tuple[int, Optional[str]]:
    row = await session.execute(
        text(
            """
            SELECT id, trace_id
              FROM orders
             WHERE platform = :p
               AND shop_id  = :s
               AND ext_order_no = :o
             LIMIT 1
            """
        ),
        {"p": platform.upper(), "s": shop_id, "o": ext_order_no},
    )
    rec = row.first()
    if rec is None:
        raise ValueError(
            f"order not found: platform={platform.upper()}, shop={shop_id}, ext_order_no={ext_order_no}"
        )
    return int(rec[0]), (str(rec[1]) if rec[1] else None)


async def reserve_flow(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ref: str,
    lines: Sequence[Mapping[str, Any]],
    trace_id: Optional[str] = None,
) -> dict:
    """
    ✅ enter_pickable（当前主线语义）

    - 不做库存裁决
    - 不做库存判断
    - 只做：
      1) 确保订单仓库已解析（执行仓 actual_warehouse_id）
      2) 将订单 status 置为 PICKABLE（仓内执行态信号）
      3) 幂等 ensure pick_task + pick_task_lines
      4) 幂等 enqueue pick_list print_job（payload 快照，可回放）
      5) 写 ORDER_PICKABLE_ENTERED 审计事件
    """
    platform_db = platform.upper()

    ext_order_no = extract_ext_order_no(platform_db, shop_id, ref)
    if not ext_order_no:
        raise ValueError(
            f"invalid ref={ref!r}, expected 'ORD:{platform_db}:{shop_id}:{{ext_order_no}}'"
        )

    warehouse_id = await resolve_warehouse_for_order(
        session,
        platform=platform_db,
        shop_id=shop_id,
        ref=ref,
    )

    order_id, trace_id_db = await _resolve_order_id_and_trace_id(
        session,
        platform=platform_db,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
    )
    trace_id_final = trace_id or trace_id_db

    target_qty: Dict[int, int] = {}
    for row in lines or ():
        item_id = row.get("item_id")
        qty = to_int_pos(row.get("qty"), default=0)
        if item_id is None or qty <= 0:
            continue
        item_id_i = int(item_id)
        target_qty[item_id_i] = target_qty.get(item_id_i, 0) + int(qty)

    if not target_qty:
        try:
            await AuditEventWriter.write(
                session,
                flow="OUTBOUND",
                event="ENTER_PICKABLE_NO_LINES",
                ref=ref,
                trace_id=trace_id_final,
                meta={
                    "platform": platform_db,
                    "shop": shop_id,
                    "warehouse_id": warehouse_id,
                    "order_id": order_id,
                },
                auto_commit=False,
            )
        except Exception:
            pass
        return {"status": "OK", "ref": ref, "lines": 0}

    try:
        await set_order_status_by_ref(
            session,
            platform=platform_db,
            shop_id=shop_id,
            ref=ref,
            new_status="PICKABLE",
        )
    except Exception:
        pass

    ensured = await resolve_order_and_ensure_task_and_print(
        session,
        platform=platform_db,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        ref=ref,
        warehouse_id=warehouse_id,
        order_id=order_id,
        target_qty=target_qty,
        trace_id=trace_id_final,
    )

    try:
        await OrderEventBus.order_pickable_entered(
            session,
            ref=ref,
            platform=platform_db,
            shop_id=shop_id,
            order_id=order_id,
            warehouse_id=warehouse_id,
            lines=len(target_qty),
            trace_id=trace_id_final,
        )

        await AuditEventWriter.write(
            session,
            flow="OUTBOUND",
            event="ENTER_PICKABLE_APPLIED",
            ref=ref,
            trace_id=trace_id_final,
            meta={
                "platform": platform_db,
                "shop": shop_id,
                "warehouse_id": warehouse_id,
                "order_id": order_id,
                "lines": len(target_qty),
                "pick_task_id": ensured.get("pick_task_id"),
                "print_job_id": ensured.get("print_job_id"),
            },
            auto_commit=False,
        )
    except Exception:
        pass

    return {
        "status": "OK",
        "ref": ref,
        "lines": len(target_qty),
        "pick_task_id": ensured.get("pick_task_id"),
        "print_job_id": ensured.get("print_job_id"),
    }
