# app/shipping_assist/shipment/audit.py
# 分拆说明：
# - 本文件从 service.py / job 侧提取 Shipment 审计写入逻辑；
# - 目标是统一收口 SHIP_COMMIT / SHIP_STATUS_UPDATE 审计事件；
# - 当前阶段只负责审计 payload 组装与写入，不承载事务提交。
from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.shared.services.audit_writer import AuditEventWriter


async def write_ship_commit_audit(
    session: AsyncSession,
    *,
    ref: str,
    platform: str,
    shop_id: str,
    trace_id: str | None,
    meta: dict[str, object] | None,
) -> None:
    payload: dict[str, object] = {
        "platform": platform.upper(),
        "shop_id": shop_id,
    }
    if meta:
        payload.update(meta)

    await AuditEventWriter.write(
        session,
        flow="OUTBOUND",
        event="SHIP_COMMIT",
        ref=ref,
        trace_id=trace_id,
        meta=payload,
        auto_commit=False,
    )


async def write_ship_status_update_audit(
    session: AsyncSession,
    *,
    ref: str,
    trace_id: str | None,
    old_status: str | None,
    new_status: str,
    delivery_time: datetime | None,
    old_error_code: str | None,
    old_error_message: str | None,
    error_code: str | None,
    error_message: str | None,
    extra_meta: dict[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {
        "old_status": old_status,
        "new_status": new_status,
        "old_error_code": old_error_code,
        "old_error_message": old_error_message,
        "error_code": error_code,
        "error_message": error_message,
        "delivery_time": delivery_time.isoformat() if delivery_time else None,
    }
    if extra_meta:
        payload.update(extra_meta)

    await AuditEventWriter.write(
        session,
        flow="OUTBOUND",
        event="SHIP_STATUS_UPDATE",
        ref=ref,
        trace_id=trace_id,
        meta=payload,
        auto_commit=False,
    )
