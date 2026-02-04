# app/services/order_ingest_routing/route_c_state.py
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_writer import AuditEventWriter


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

    说明：
    - 参数 detail 仅用于审计/日志（不写入 order_fulfillment）
    """
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
    """
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
