# app/wms/outbound/services/order_reserve_flow_reserve.py
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problem import raise_problem
from app.wms.shared.services.audit_writer import AuditEventWriter
from app.oms.services.order_event_bus import OrderEventBus
from app.oms.services.order_trace_helper import set_order_status_by_ref
from app.oms.services.order_utils import to_int_pos
from app.wms.outbound.services.order_reserve_flow_types import extract_ext_order_no

from app.wms.outbound.services.pick_task_auto import resolve_order_and_ensure_task_and_print


async def resolve_warehouse_for_order(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ref: str,
) -> int:
    """
    Phase 5：执行仓事实只来自 order_fulfillment.actual_warehouse_id（authority）。

    规则（硬）：
    - 进入执行链路必须已绑定 actual_warehouse_id
    - 若 actual_warehouse_id 为空：
        * 若 fulfillment_status/blocked_reasons 表明 BLOCKED → 409（携带 blocked_reasons）
        * 否则 → 409（未分配执行仓，禁止进入执行链路）
    - 若订单不存在 → 404
    """
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
              f.planned_warehouse_id  AS planned_warehouse_id,
              f.actual_warehouse_id   AS actual_warehouse_id,
              f.fulfillment_status    AS fulfillment_status,
              f.blocked_reasons       AS blocked_reasons
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
        raise_problem(
            status_code=404,
            error_code="order_not_found",
            message="订单不存在，无法解析执行仓。",
            context={"platform": plat, "shop_id": shop_id, "ext_order_no": ext_order_no, "ref": ref},
            details=[],
            next_actions=[],
        )
        return 0

    planned_wh = rec[0]
    actual_wh = rec[1]
    fulfillment_status = rec[2]
    blocked_reasons = rec[3]

    if actual_wh is None or int(actual_wh) == 0:
        extra: Dict[str, Any] = {
            "platform": plat,
            "shop_id": shop_id,
            "ext_order_no": ext_order_no,
            "ref": ref,
            "fulfillment_status": fulfillment_status,
            "blocked_reasons": blocked_reasons,
            "planned_warehouse_id": int(planned_wh) if planned_wh is not None else None,
        }

        code = (
            "fulfillment_blocked"
            if (fulfillment_status and "BLOCK" in str(fulfillment_status).upper())
            else "fulfillment_unassigned"
        )
        msg = (
            "订单履约被阻断，禁止进入执行链路。"
            if code == "fulfillment_blocked"
            else "订单尚未绑定执行仓（actual_warehouse_id），禁止进入执行链路。"
        )

        raise_problem(
            status_code=409,
            error_code=code,
            message=msg,
            context=extra,
            details=[{"blocked_reasons": blocked_reasons}] if blocked_reasons else [],
            next_actions=[{"action": "route", "label": "运行路由/改派"}],
        )
        return 0

    return int(actual_wh)


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
        raise_problem(
            status_code=404,
            error_code="order_not_found",
            message="订单不存在。",
            context={"platform": platform.upper(), "shop_id": shop_id, "ext_order_no": ext_order_no},
            details=[],
            next_actions=[],
        )
        return 0, None
    return int(rec[0]), (str(rec[1]) if rec[1] else None)


async def _mark_execution_stage_pick(
    session: AsyncSession,
    *,
    order_id: int,
) -> None:
    """
    Phase 5：订单进入拣货主线后，将 execution_stage 收口为 PICK。

    规则：
    - NULL -> PICK
    - PICK 保持
    - SHIP 不回退
    """
    res = await session.execute(
        text(
            """
            UPDATE order_fulfillment
               SET execution_stage = CASE
                   WHEN execution_stage IS NULL THEN 'PICK'
                   WHEN execution_stage = 'PICK' THEN 'PICK'
                   WHEN execution_stage = 'SHIP' THEN 'SHIP'
                   ELSE execution_stage
               END,
                   updated_at = now()
             WHERE order_id = :oid
            """
        ),
        {"oid": int(order_id)},
    )

    # ✅ 硬门禁：进入拣货主线必须写入执行阶段真相
    # 正常情况下 order_fulfillment 必须存在（否则 resolve_warehouse_for_order 会拦）。
    if int(getattr(res, "rowcount", 0) or 0) <= 0:
        raise_problem(
            status_code=409,
            error_code="execution_stage_write_failed",
            message="进入拣货主线失败：无法写入执行阶段（execution_stage=PICK）。",
            context={"order_id": int(order_id)},
            details=[],
            next_actions=[{"action": "inspect_fulfillment", "label": "检查订单履约记录"}],
        )


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
    enter_pickable（主线语义）

    - 不做库存裁决
    - 不做库存判断
    - 只做：
      1) 确保执行仓已绑定（必须为 actual_warehouse_id）
      2) 将订单 status 置为 PICKABLE（影子态，后续可淡出）
      3) 幂等 ensure pick_task + pick_task_lines
      4) 幂等 enqueue pick_list print_job（payload 快照，可回放）
      5) 写 ORDER_PICKABLE_ENTERED 审计事件
      6) execution_stage 收口为 PICK（执行阶段真相，硬门禁）
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

    # ✅ 不再吞异常：execution_stage 写入失败必须暴露（失败栈优先修复）
    await _mark_execution_stage_pick(session, order_id=order_id)

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
