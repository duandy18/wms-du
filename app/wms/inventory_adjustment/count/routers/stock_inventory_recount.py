# app/wms/reconciliation/routers/stock_inventory_recount.py
from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.wms.inventory_adjustment.count.services.count_freeze_guard_service import (
    ensure_warehouse_not_frozen,
)

router = APIRouter()


def _make_scan_ref(device_id: Optional[str], occurred_at: datetime, warehouse_id: Optional[int]) -> str:
    dev = (device_id or "device").lower()
    wh = f"wh:{warehouse_id}" if warehouse_id is not None else "wh:unknown"
    iso = occurred_at.astimezone(timezone.utc).isoformat()
    return f"scan:{dev}:{iso}:{wh}".lower()


class StockRecountRequest(BaseModel):
    item_id: int = Field(..., description="物料ID")
    warehouse_id: int = Field(..., ge=1, description="仓库ID")
    lot_code: Optional[str] = Field(None, description="Lot 展示码（优先使用；等价于 batch_code）")
    batch_code: Optional[str] = Field(None, description="批次（无批次槽位传 null）")
    actual: int = Field(..., ge=0, description="实际数量")
    ctx: Dict[str, Any] | None = None


async def _insert_event(session: AsyncSession, *, source: str, message: str, occurred_at: datetime) -> int:
    payload = json.dumps({"scan_ref": message}, ensure_ascii=False)
    row = await session.execute(
        text(
            """
            INSERT INTO event_log(source, message, occurred_at)
            VALUES (:src, :msg, :ts)
            RETURNING id
            """
        ),
        {"src": source, "msg": payload, "ts": occurred_at},
    )
    return int(row.scalar_one())


@router.post("/stock/inventory/recount")
async def stock_recount(
    req: StockRecountRequest,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    运维盘点：把 item@warehouse@batch_code 的 qty 校正为 actual。

    Phase 4E 真收口：
    - 禁止读取 legacy stocks
    - current 余额统一来自 stocks_lot
    - batch_code 为展示码（lots.lot_code），按 NULL 语义用 IS NOT DISTINCT FROM
    """
    device_id = (req.ctx or {}).get("device_id") if isinstance(req.ctx, dict) else None
    occurred_at = datetime.now(timezone.utc)
    scan_ref = _make_scan_ref(device_id, occurred_at, req.warehouse_id)

    # Phase M-4 governance：lot_code 正名；batch_code 兼容字段
    code = getattr(req, "lot_code", None) or req.batch_code

    try:
        from app.wms.stock.services.stock_service import StockService  # type: ignore
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"stock service missing: {e}")

    svc = StockService()

    try:
        await ensure_warehouse_not_frozen(
            session,
            warehouse_id=int(req.warehouse_id),
        )

        row = await session.execute(
            text(
                """
                SELECT COALESCE(SUM(s.qty), 0) AS on_hand
                  FROM stocks_lot s
                  LEFT JOIN lots lo
                    ON lo.id = s.lot_id
                 WHERE s.item_id=:i
                   AND s.warehouse_id=:w
                   AND lo.lot_code IS NOT DISTINCT FROM :c
                """
            ),
            {"i": int(req.item_id), "w": int(req.warehouse_id), "c": code},
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
                batch_code=code,
            )

        ev_id = await _insert_event(
            session,
            source="stock_recount",
            message=scan_ref,
            occurred_at=occurred_at,
        )

        await session.commit()

        return {
            "scan_ref": scan_ref,
            "event_id": ev_id,
            "on_hand": on_hand,
            "actual": int(req.actual),
            "delta": delta,
            "committed": True,
        }

    except HTTPException:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise
