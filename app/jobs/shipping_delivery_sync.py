# app/jobs/shipping_delivery_sync.py
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal  # 你项目里定义的 async 会话工厂
from app.services.audit_writer import AuditEventWriter

# -------- 平台状态映射表（需你按实际平台补充） --------

# 内部终态：这些一旦写入就不再被平台状态覆盖
INTERNAL_FINAL_STATUSES = {"DELIVERED", "LOST", "RETURNED"}

# 这里用“平台 → 内部状态 → 平台状态集合”的形式
# ⚠️ 里面的字符串请按你真实的平台状态码/文案调整
PLATFORM_STATUS_MAP: Dict[str, Dict[str, Sequence[str]]] = {
    # 示例：拼多多
    "PDD": {
        "DELIVERED": ["已签收", "TRADE_SUCCESS", "TRADE_FINISHED"],
        "RETURNED": ["已退货", "REFUND_SUCCESS"],
        "LOST": ["包裹丢失", "LOST"],
    },
    # 示例：京东
    "JD": {
        "DELIVERED": ["已签收", "FINISHED_L"],
        "RETURNED": ["已退货", "RETURNED"],
        "LOST": ["丢失", "LOST"],
    },
    # 其他平台按需扩展
}


@dataclass
class PlatformOrderStatus:
    platform: str
    shop_id: str
    ext_order_no: str
    platform_status: str  # 平台原始状态码/文案
    internal_status: Optional[str]  # 映射后的内部状态：DELIVERED/RETURNED/LOST/None
    delivered_at: Optional[datetime]  # 若能从平台拿到签收时间就丢这里
    raw_payload: Dict[str, Any]


def _normalize_platform_status(platform: str, raw_status: str) -> Optional[str]:
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


async def _get_latest_platform_status_for_order(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    order_ref: str,
) -> Optional[PlatformOrderStatus]:
    """
    从 platform_events 中抓取当前订单最近一次 ORDER_STATUS 事件。

    约定：
      - event_type = 'ORDER_STATUS'
      - payload 至少包含：
          * ext_order_no
          * platform_status
          * （可选）delivered_at / delivered_time / sign_time
      - dedup_key 建议设置成 order_ref（ORD:{PLAT}:{shop_id}:{ext}），方便 join。
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

    internal = _normalize_platform_status(plat, platform_status)

    return PlatformOrderStatus(
        platform=plat,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        platform_status=platform_status,
        internal_status=internal,
        delivered_at=delivered_at,
        raw_payload=payload,
    )


async def _update_shipping_record_status_from_platform(
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
    # 1）内部状态映射失败，直接跳过
    new_status = plat_status.internal_status
    if not new_status:
        return False

    current_key = (current_status or "").upper()
    # 2）如果当前已经是终态（DELIVERED / LOST / RETURNED），不再覆盖
    if current_key in INTERNAL_FINAL_STATUSES:
        return False

    # 3）如果状态没变，也不必写
    if current_key == new_status:
        return False

    # 4）delivery_time：优先平台时间，其次保留原值，再其次 now()
    if plat_status.delivered_at and new_status == "DELIVERED":
        delivery_time = plat_status.delivered_at
    elif current_delivery_time:
        delivery_time = current_delivery_time
    elif new_status == "DELIVERED":
        delivery_time = datetime.now(timezone.utc)
    else:
        delivery_time = current_delivery_time  # 非 DELIVERED 就不强制时间

    # 5）合并 meta（保留原来的，附上 platform_status 和 payload 摘要）
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

    # 6）更新 shipping_records
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

    # 7）写审计事件 OUTBOUND / SHIP_STATUS_UPDATE
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


async def run_once(session: AsyncSession) -> int:
    """
    扫描 shipping_records 中尚未终态的记录，通过 platform_events 同步状态。

    返回：本次实际更新的记录条数。
    """
    # 只挑候选：status IS NULL 或 IN_TRANSIT
    sql = text(
        """
        SELECT
          id,
          order_ref,
          platform,
          shop_id,
          status,
          delivery_time,
          trace_id
        FROM shipping_records
        WHERE status IS NULL
           OR status = 'IN_TRANSIT'
        ORDER BY created_at ASC, id ASC
        LIMIT 500
        """
    )
    rows = (await session.execute(sql)).mappings().all()
    if not rows:
        return 0

    updated = 0

    for r in rows:
        rec_id = int(r["id"])
        order_ref = str(r["order_ref"])
        platform = str(r["platform"])
        shop_id = str(r["shop_id"])
        current_status: Optional[str] = r.get("status")
        current_delivery_time: Optional[datetime] = r.get("delivery_time")
        trace_id: Optional[str] = r.get("trace_id")

        plat_status = await _get_latest_platform_status_for_order(
            session,
            platform=platform,
            shop_id=shop_id,
            order_ref=order_ref,
        )
        if not plat_status:
            continue

        changed = await _update_shipping_record_status_from_platform(
            session,
            record_id=rec_id,
            current_status=current_status,
            current_delivery_time=current_delivery_time,
            order_ref=order_ref,
            trace_id=trace_id,
            plat_status=plat_status,
        )
        if changed:
            updated += 1

    await session.commit()
    return updated


async def main() -> None:
    # 使用 AsyncSessionLocal 作为异步会话工厂
    async with AsyncSessionLocal() as session:
        updated = await run_once(session)
        print(f"[shipping_delivery_sync] updated records: {updated}")


if __name__ == "__main__":
    asyncio.run(main())
