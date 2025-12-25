# app/jobs/shipping_delivery_sync_runner.py
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal  # 你项目里定义的 async 会话工厂

from app.jobs.shipping_delivery_sync_apply import update_shipping_record_status_from_platform
from app.jobs.shipping_delivery_sync_platform import get_latest_platform_status_for_order


async def run_once(session: AsyncSession) -> int:
    """
    扫描 shipping_records 中尚未终态的记录，通过 platform_events 同步状态。

    返回：本次实际更新的记录条数。
    """
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

        plat_status = await get_latest_platform_status_for_order(
            session,
            platform=platform,
            shop_id=shop_id,
            order_ref=order_ref,
        )
        if not plat_status:
            continue

        changed = await update_shipping_record_status_from_platform(
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
    async with AsyncSessionLocal() as session:
        updated = await run_once(session)
        print(f"[shipping_delivery_sync] updated records: {updated}")


def run_cli() -> None:
    asyncio.run(main())
