# app/services/order_ingest_routing/route_c_state.py
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_writer import AuditEventWriter


async def _load_execution_guard(
    session: AsyncSession, *, order_id: int
) -> Tuple[Optional[int], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Phase 5+（路 A）：路由域写入必须尊重执行域事实（authority）。

    返回：
    - actual_warehouse_id：执行仓锚点（非空代表执行已绑定/已开始）
    - execution_stage：显式执行阶段真相（PICK/SHIP）
    - ship_committed_at：进入出库裁决链路锚点（事实）
    - shipped_at：出库完成时间（事实）
    - fulfillment_status：路由/阻断/人工干预语义（不再承载 SHIP_COMMITTED/SHIPPED）
    """
    row = (
        await session.execute(
            text(
                """
                SELECT
                  actual_warehouse_id,
                  execution_stage,
                  ship_committed_at,
                  shipped_at,
                  fulfillment_status
                FROM order_fulfillment
                WHERE order_id = :oid
                LIMIT 1
                """
            ),
            {"oid": int(order_id)},
        )
    ).first()
    if not row:
        return None, None, None, None, None

    actual_wh = int(row[0]) if row[0] is not None else None
    execution_stage = str(row[1]) if row[1] is not None else None
    ship_committed_at = str(row[2]) if row[2] is not None else None
    shipped_at = str(row[3]) if row[3] is not None else None
    st = str(row[4]) if row[4] is not None else None
    return actual_wh, execution_stage, ship_committed_at, shipped_at, st


def _is_execution_started(
    actual_wh: Optional[int],
    execution_stage: Optional[str],
    ship_committed_at: Optional[str],
    shipped_at: Optional[str],
) -> bool:
    """
    执行域已开始（路由域不得回写破坏事实）的判定（路 A）：

    - actual_warehouse_id 已存在（执行仓事实已绑定），或
    - execution_stage 已进入 SHIP（已进入出库裁决链路），或
    - ship_committed_at 已存在（出库锚点事实），或
    - shipped_at 已存在（已完成出库事实）
    """
    if actual_wh is not None and int(actual_wh) != 0:
        return True

    stg = (execution_stage or "").strip().upper()
    if stg == "SHIP":
        return True

    if ship_committed_at:
        return True
    if shipped_at:
        return True

    return False


async def mark_fulfillment_blocked(
    session: AsyncSession,
    *,
    order_id: int,
    order_ref: str,
    trace_id: Optional[str],
    platform_norm: str,
    shop_id: str,
    reasons_json: str,
    detail: str,
    province: Optional[str],
    city: Optional[str],
    service_warehouse_id: Optional[int],
    meta_extra: Optional[Dict[str, Any]] = None,
    auto_commit: bool = False,
) -> dict:
    """
    Route C：统一的 BLOCKED 写入 + 审计事件写入 + 返回 payload。

    一步到位迁移后：
    - orders 表不再承载履约列
    - BLOCKED 写入 order_fulfillment（最小事实）：
        - fulfillment_status = 'FULFILLMENT_BLOCKED'
        - blocked_reasons（仅原因，不落库 detail）
        - planned_warehouse_id = service_warehouse_id（计划/归属快照）
        - actual_warehouse_id = NULL（BLOCKED 时不应有实际仓事实）

    Phase 5+ 执行域护栏（硬，路 A）：
    - 一旦执行已开始（actual 已绑定 / 已进入 SHIP / ship_committed_at/shipped_at 已存在），路由域不得回写破坏执行事实：
      - 不允许把 actual 置 NULL
      - 不允许把 fulfillment_status 覆盖为 BLOCKED
    - 这种场景下：no-op（返回 SKIPPED），避免重复 ingest/补偿把执行事实“降级”。

    说明：
    - 参数 detail 仅用于审计/日志（不写入 order_fulfillment）
    """
    actual_wh, execution_stage, ship_committed_at, shipped_at, _existing_st = await _load_execution_guard(
        session, order_id=int(order_id)
    )
    if _is_execution_started(actual_wh, execution_stage, ship_committed_at, shipped_at):
        return {
            "status": "SKIPPED",
            "reason": "EXECUTION_ALREADY_STARTED",
            "service_warehouse_id": int(service_warehouse_id) if service_warehouse_id is not None else None,
            "province": province,
            "city": city,
        }

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
                :pwid,
                NULL,
                'FULFILLMENT_BLOCKED',
                CAST(:reasons AS jsonb),
                now()
            )
            ON CONFLICT (order_id)
            DO UPDATE SET
                planned_warehouse_id = EXCLUDED.planned_warehouse_id,
                actual_warehouse_id = NULL,
                fulfillment_status = EXCLUDED.fulfillment_status,
                blocked_reasons = EXCLUDED.blocked_reasons,
                updated_at = now()
            """
        ),
        {
            "oid": int(order_id),
            "pwid": int(service_warehouse_id) if service_warehouse_id is not None else None,
            "reasons": reasons_json,
        },
    )

    meta: Dict[str, Any] = {
        "platform": platform_norm,
        "shop": shop_id,
        "province": province,
        "city": city,
        "service_warehouse_id": int(service_warehouse_id) if service_warehouse_id is not None else None,
    }
    if detail:
        meta["detail"] = str(detail)
    if meta_extra:
        meta.update(meta_extra)

    try:
        await AuditEventWriter.write(
            session,
            flow="OUTBOUND",
            event="FULFILLMENT_BLOCKED",
            ref=order_ref,
            trace_id=trace_id,
            meta=meta,
            auto_commit=auto_commit,
        )
    except Exception:
        pass

    payload: Dict[str, Any] = {
        "status": "FULFILLMENT_BLOCKED",
        "service_warehouse_id": int(service_warehouse_id) if service_warehouse_id is not None else None,
        "province": province,
        "city": city,
        "considered": meta_extra.get("considered", []) if meta_extra else [],
    }
    if meta_extra and "reason" in meta_extra:
        payload["reason"] = meta_extra["reason"]
    if meta_extra and "mode" in meta_extra:
        payload["mode"] = meta_extra["mode"]
    return payload


async def mark_service_assigned(
    session: AsyncSession,
    *,
    order_id: int,
    order_ref: str,
    trace_id: Optional[str],
    platform_norm: str,
    shop_id: str,
    service_warehouse_id: int,
    province: str,
    city: Optional[str],
    mode: str,
    auto_commit: bool = False,
) -> dict:
    """
    一步到位迁移后：
    - SERVICE_ASSIGNED 写入 order_fulfillment（最小事实）：
        - planned_warehouse_id = service_warehouse_id（计划/归属快照）
        - fulfillment_status = 'SERVICE_ASSIGNED'
        - blocked_reasons = NULL
    - 不在此阶段写 actual_warehouse_id（实际仓），避免把“计划”误当“事实”。

    Phase 5+ 执行域护栏（硬，路 A）：
    - 一旦执行已开始（actual 已绑定 / 已进入 SHIP / ship_committed_at/shipped_at 已存在），路由域不得回写破坏执行事实：
      - 不允许把 actual 置 NULL
      - 不允许把 fulfillment_status 覆盖为 SERVICE_ASSIGNED
    - 这种场景下：no-op（返回 SKIPPED），避免重复 ingest/补偿把执行事实“降级”。
    """
    actual_wh, execution_stage, ship_committed_at, shipped_at, _existing_st = await _load_execution_guard(
        session, order_id=int(order_id)
    )
    if _is_execution_started(actual_wh, execution_stage, ship_committed_at, shipped_at):
        return {
            "status": "SKIPPED",
            "reason": "EXECUTION_ALREADY_STARTED",
            "service_warehouse_id": int(service_warehouse_id),
            "province": province,
            "city": city,
            "mode": mode,
        }

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
                :pwid,
                NULL,
                'SERVICE_ASSIGNED',
                NULL,
                now()
            )
            ON CONFLICT (order_id)
            DO UPDATE SET
                planned_warehouse_id = EXCLUDED.planned_warehouse_id,
                actual_warehouse_id = NULL,
                fulfillment_status = EXCLUDED.fulfillment_status,
                blocked_reasons = NULL,
                updated_at = now()
            """
        ),
        {"pwid": int(service_warehouse_id), "oid": int(order_id)},
    )

    try:
        await AuditEventWriter.write(
            session,
            flow="OUTBOUND",
            event="SERVICE_WAREHOUSE_ASSIGNED",
            ref=order_ref,
            trace_id=trace_id,
            meta={
                "platform": platform_norm,
                "shop": shop_id,
                "service_warehouse_id": int(service_warehouse_id),
                "province": province,
                "city": city,
                "mode": mode,
            },
            auto_commit=auto_commit,
        )
    except Exception:
        pass

    return {
        "status": "SERVICE_ASSIGNED",
        "service_warehouse_id": int(service_warehouse_id),
        "province": province,
        "city": city,
        "mode": mode,
    }
