# app/api/routers/stock_inventory.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session

router = APIRouter()


def _make_scan_ref(device_id: Optional[str], occurred_at: datetime, warehouse_id: Optional[int]) -> str:
    dev = (device_id or "device").lower()
    wh = f"wh:{warehouse_id}" if warehouse_id is not None else "wh:unknown"
    iso = occurred_at.astimezone(timezone.utc).isoformat()
    return f"scan:{dev}:{iso}:{wh}".lower()


class StockRecountRequest(BaseModel):
    item_id: int = Field(..., description="物料ID")
    warehouse_id: int = Field(..., ge=1, description="仓库ID")
    batch_code: Optional[str] = Field(None, description="批次（无批次槽位传 null）")
    actual: int = Field(..., ge=0, description="实际数量")
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
async def stock_recount(
    req: StockRecountRequest,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    运维盘点：把 item@warehouse@batch_code 的 qty 校正为 actual。
    """
    device_id = (req.ctx or {}).get("device_id") if isinstance(req.ctx, dict) else None
    occurred_at = datetime.now(timezone.utc)
    scan_ref = _make_scan_ref(device_id, occurred_at, req.warehouse_id)

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
                 WHERE item_id=:i
                   AND warehouse_id=:w
                   AND batch_code IS NOT DISTINCT FROM :c
                """
            ),
            {"i": int(req.item_id), "w": int(req.warehouse_id), "c": req.batch_code},
        )
        on_hand = int(row.scalar_one() or 0)
        delta = int(req.actual) - on_hand

        if delta != 0:
            await svc.adjust(
                session=session,
                item_id=int(req.item_id),
                warehouse_id=int(req.warehouse_id),
                delta=delta,
                reason="COUNT",
                ref=scan_ref,
                batch_code=req.batch_code,
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
