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
    语义不变：BLOCKED 时不写 orders.warehouse_id；service_warehouse_id 可写可不写（按调用传入）。
    """
    await session.execute(
        text(
            """
            UPDATE orders
               SET fulfillment_status = 'FULFILLMENT_BLOCKED',
                   blocked_reasons    = CAST(:reasons AS jsonb),
                   blocked_detail     = :detail,
                   service_warehouse_id = :swid,
                   fulfillment_warehouse_id = NULL
             WHERE id = :oid
            """
        ),
        {
            "oid": int(order_id),
            "reasons": reasons_json,
            "detail": detail,
            "swid": int(service_warehouse_id) if service_warehouse_id is not None else None,
        },
    )

    meta: Dict[str, Any] = {
        "platform": platform_norm,
        "shop": shop_id,
        "province": province,
        "city": city,
        "service_warehouse_id": int(service_warehouse_id) if service_warehouse_id is not None else None,
    }
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
    ✅ 新世界观：只写“服务归属事实”
    - 写 orders.service_warehouse_id
    - 不写 orders.warehouse_id（实际出库仓由人工决定）
    - fulfillment_status 使用 SERVICE_ASSIGNED（避免误导为“库存已校验可履约”）
    """
    await session.execute(
        text(
            """
            UPDATE orders
               SET service_warehouse_id = :swid,
                   fulfillment_status = 'SERVICE_ASSIGNED',
                   blocked_reasons = NULL,
                   blocked_detail = NULL
             WHERE id = :oid
            """
        ),
        {"swid": int(service_warehouse_id), "oid": int(order_id)},
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


async def mark_ready_to_fulfill(
    session: AsyncSession,
    *,
    order_id: int,
    order_ref: str,
    trace_id: Optional[str],
    platform_norm: str,
    shop_id: str,
    warehouse_id: int,
    province: str,
    city: Optional[str],
    mode: str,
    auto_commit: bool = False,
) -> dict:
    """
    （历史兼容）Route C：READY 写入 + 审计事件写入 + 返回 payload。
    语义：READY 时写 orders.warehouse_id / service_warehouse_id / fulfillment_warehouse_id。
    """
    await session.execute(
        text(
            """
            UPDATE orders
               SET warehouse_id = :wid,
                   service_warehouse_id = :wid,
                   fulfillment_warehouse_id = :wid,
                   fulfillment_status = 'READY_TO_FULFILL',
                   blocked_reasons = NULL,
                   blocked_detail = NULL
             WHERE id = :oid
            """
        ),
        {"wid": int(warehouse_id), "oid": int(order_id)},
    )

    try:
        await AuditEventWriter.write(
            session,
            flow="OUTBOUND",
            event="WAREHOUSE_ROUTED",
            ref=order_ref,
            trace_id=trace_id,
            meta={
                "platform": platform_norm,
                "shop": shop_id,
                "warehouse_id": int(warehouse_id),
                "province": province,
                "city": city,
                "reason": "service_hit",
                "considered": [int(warehouse_id)],
                "mode": mode,
            },
            auto_commit=auto_commit,
        )
    except Exception:
        pass

    return {
        "status": "READY_TO_FULFILL",
        "warehouse_id": int(warehouse_id),
        "service_warehouse_id": int(warehouse_id),
        "province": province,
        "city": city,
        "reason": "service_hit",
        "considered": [int(warehouse_id)],
        "mode": mode,
    }
