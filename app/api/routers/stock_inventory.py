# app/api/routers/stock_inventory.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.scan_utils import make_scan_ref

router = APIRouter()


class StockRecountRequest(BaseModel):
    item_id: int = Field(..., description="物料ID")
    location_id: int = Field(..., description="库位ID")
    actual: int = Field(..., description="实际数量")
    ctx: Dict[str, Any] | None = None


async def _insert_event(session: AsyncSession, *, source: str, message: str, occurred_at: datetime) -> int:
    row = await session.execute(
        text(
            """
            INSERT INTO event_log(source, message, occurred_at)
            VALUES (:src, :msg, :ts)
            RETURNING id
            """
        ),
        {"src": source, "msg": message, "ts": occurred_at},
    )
    return int(row.scalar_one())


@router.post("/stock/inventory/recount")
async def stock_recount(req: StockRecountRequest, session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    """把某 item@location 的账面调整为 actual（执行一条 COUNT 差额账）。"""
    device_id = (req.ctx or {}).get("device_id") if isinstance(req.ctx, dict) else None
    occurred_at = datetime.now(timezone.utc)
    scan_ref = make_scan_ref(device_id, occurred_at, req.location_id)

    try:
        from app.services.stock_service import StockService  # type: ignore
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"stock service missing: {e}")

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
            {"i": int(req.item_id), "l": int(req.location_id)},
        )
        on_hand = int(row.scalar_one() or 0)
        delta = int(req.actual) - on_hand

        if delta != 0:
            await svc.adjust(
                session=session,
                item_id=int(req.item_id),
                location_id=int(req.location_id),
                delta=delta,
                reason="COUNT",
                ref=scan_ref,
            )

        ev_id = await _insert_event(session, source="stock_recount", message=scan_ref, occurred_at=occurred_at)

    return {
        "scan_ref": scan_ref,
        "event_id": ev_id,
        "on_hand": on_hand,
        "actual": int(req.actual),
        "delta": delta,
        "committed": True,
    }
