# app/jobs/shipping_delivery_sync_platform.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.shipping_delivery_sync_config import PLATFORM_STATUS_MAP
from app.jobs.shipping_delivery_sync_types import PlatformOrderStatus


def normalize_platform_status(platform: str, raw_status: str) -> Optional[str]:
    """
    将平台原始状态映射为内部状态：
      - DELIVERED / RETURNED / LOST / None
    """
    plat = platform.upper()
    raw = (raw_status or "").strip()
    if not raw:
        return None

    mapping = PLATFORM_STATUS_MAP.get(plat)
    if not mapping:
        return None

    for internal, candidates in mapping.items():
        for c in candidates:
            if not c:
                continue
            if raw == c:
                return internal
            # 宽松：包含关键字也算匹配
            if c in raw:
                return internal

    return None


async def get_latest_platform_status_for_order(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    order_ref: str,
) -> Optional[PlatformOrderStatus]:
    """
    从 platform_events 中抓取当前订单最近一次 ORDER_STATUS 事件。
    """
    plat = platform.upper()

    # 解析 ext_order_no：order_ref = ORD:{PLAT}:{shop_id}:{ext}
    parts = order_ref.split(":", 3)
    ext_order_no = parts[3] if len(parts) == 4 else order_ref

    sql = text(
        """
        SELECT
          id,
          payload,
          occurred_at
        FROM platform_events
        WHERE platform = :platform
          AND shop_id = :shop_id
          AND event_type = 'ORDER_STATUS'
          AND (dedup_key = :order_ref OR payload->>'ext_order_no' = :ext_order_no)
        ORDER BY occurred_at DESC, id DESC
        LIMIT 1
        """
    )
    row = (
        (
            await session.execute(
                sql,
                {
                    "platform": plat,
                    "shop_id": shop_id,
                    "order_ref": order_ref,
                    "ext_order_no": ext_order_no,
                },
            )
        )
        .mappings()
        .first()
    )

    if not row:
        return None

    payload: Dict[str, Any] = row["payload"] or {}
    platform_status = str(
        payload.get("platform_status") or payload.get("order_status") or payload.get("status") or ""
    )

    delivered_at_raw = (
        payload.get("delivered_at") or payload.get("delivered_time") or payload.get("sign_time")
    )
    delivered_at: Optional[datetime] = None
    if isinstance(delivered_at_raw, str):
        try:
            delivered_at = datetime.fromisoformat(delivered_at_raw)
            if delivered_at.tzinfo is None:
                delivered_at = delivered_at.replace(tzinfo=timezone.utc)
        except Exception:
            delivered_at = None

    internal = normalize_platform_status(plat, platform_status)

    return PlatformOrderStatus(
        platform=plat,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        platform_status=platform_status,
        internal_status=internal,
        delivered_at=delivered_at,
        raw_payload=payload,
    )
