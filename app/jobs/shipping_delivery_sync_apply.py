# app/jobs/shipping_delivery_sync_apply.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.shipping_delivery_sync_config import INTERNAL_FINAL_STATUSES
from app.jobs.shipping_delivery_sync_types import PlatformOrderStatus
from app.services.audit_writer import AuditEventWriter


async def update_shipping_record_status_from_platform(
    session: AsyncSession,
    *,
    record_id: int,
    current_status: Optional[str],
    current_delivery_time: Optional[datetime],
    order_ref: str,
    trace_id: Optional[str],
    plat_status: PlatformOrderStatus,
) -> bool:
    """
    根据平台状态更新 shipping_records + 写审计事件。

    返回：
      True  = 有更新
      False = 未更新（状态未变 / 无法映射 / 当前已是终态）
    """
    new_status = plat_status.internal_status
    if not new_status:
        return False

    current_key = (current_status or "").upper()
    if current_key in INTERNAL_FINAL_STATUSES:
        return False

    if current_key == new_status:
        return False

    if plat_status.delivered_at and new_status == "DELIVERED":
        delivery_time = plat_status.delivered_at
    elif current_delivery_time:
        delivery_time = current_delivery_time
    elif new_status == "DELIVERED":
        delivery_time = datetime.now(timezone.utc)
    else:
        delivery_time = current_delivery_time

    select_sql = text(
        """
        SELECT meta, error_code, error_message
          FROM shipping_records
         WHERE id = :id
        """
    )
    row = (await session.execute(select_sql, {"id": record_id})).mappings().first()
    old_meta = (row.get("meta") or {}) if row else {}
    error_code = row.get("error_code") if row else None
    error_message = row.get("error_message") if row else None

    new_meta = dict(old_meta or {})
    new_meta.setdefault("platform", plat_status.platform)
    new_meta.setdefault("shop_id", plat_status.shop_id)
    new_meta["platform_status"] = plat_status.platform_status
    new_meta["platform_status_synced_at"] = datetime.now(timezone.utc).isoformat()
    new_meta["platform_payload"] = {
        "ext_order_no": plat_status.ext_order_no,
        "status": plat_status.platform_status,
    }

    import json

    update_sql = text(
        """
        UPDATE shipping_records
           SET status = :status,
               delivery_time = :delivery_time,
               meta = :meta
         WHERE id = :id
        """
    )
    await session.execute(
        update_sql,
        {
            "id": record_id,
            "status": new_status,
            "delivery_time": delivery_time,
            "meta": json.dumps(new_meta, ensure_ascii=False),
        },
    )

    await AuditEventWriter.write(
        session,
        flow="OUTBOUND",
        event="SHIP_STATUS_UPDATE",
        ref=order_ref,
        trace_id=trace_id,
        meta={
            "old_status": current_status,
            "new_status": new_status,
            "delivery_time": delivery_time.isoformat() if delivery_time else None,
            "platform": plat_status.platform,
            "shop_id": plat_status.shop_id,
            "platform_status": plat_status.platform_status,
            "error_code": error_code,
            "error_message": error_message,
        },
        auto_commit=False,
    )

    return True
