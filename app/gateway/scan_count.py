# app/gateway/scan_count.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.scan_utils import parse_barcode, make_scan_ref


async def handle_scan_count(
    session: AsyncSession,
    *,
    barcode: str,
    ctx: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    扫码盘点：条码形如 `LOC:1 ITEM:3001 QTY:3`
    逻辑：on_hand = SUM(stocks.qty), delta = actual - on_hand；delta != 0 则写一条 COUNT。
    """
    parsed = parse_barcode(barcode)
    item_id = int(parsed.get("item_id") or 0)
    location_id = int(parsed.get("location_id") or 0)
    actual = int(parsed.get("qty") or 0)

    if not item_id or not location_id:
        raise ValueError("count requires ITEM and LOC in barcode")

    device_id = (ctx or {}).get("device_id") if isinstance(ctx, dict) else None
    occurred_at = datetime.now(timezone.utc)
    scan_ref = make_scan_ref(device_id, occurred_at, location_id)

    # 延迟导入以避免循环
    from app.services.stock_service import StockService  # type: ignore

    svc = StockService()

    async with session.begin():
        row = await session.execute(
            text(
                """
                SELECT COALESCE(SUM(qty), 0) AS on_hand
                  FROM stocks
                 WHERE item_id=:i AND location_id=:l
                """
            ),
            {"i": item_id, "l": location_id},
        )
        on_hand = int(row.scalar_one() or 0)
        delta = int(actual) - on_hand

        if delta != 0:
            await svc.adjust(
                session=session,
                item_id=item_id,
                location_id=location_id,
                delta=delta,
                reason="COUNT",
                ref=scan_ref,
            )

        await session.execute(
            text(
                """
                INSERT INTO event_log(source, message, occurred_at)
                VALUES ('scan_count_commit', :msg, :ts)
                """
            ),
            {"msg": scan_ref, "ts": occurred_at},
        )

    return {
        "scan_ref": scan_ref,
        "occurred_at": occurred_at.isoformat(),
        "on_hand": on_hand,
        "counted": actual,
        "delta": delta,
        "committed": True,
    }
