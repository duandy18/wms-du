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


# ================================================================
# 本地化的 scan_ref 生成器
# （用于库存运维接口，避免依赖 app/api/routers/scan_utils）
# ================================================================
def _make_scan_ref(
    device_id: Optional[str],
    occurred_at: datetime,
    location_id: Optional[int],
) -> str:
    """
    统一生成 scan_ref（小写），仅用于 stock_recount 调试/审计。
    格式与旧 scan_utils 保持一致，避免破坏既有行为：
        scan:{device}:{ISO8601}:{loc:X}
    """
    dev = (device_id or "device").lower()
    loc = f"loc:{location_id}" if location_id is not None else "loc:unknown"
    iso = occurred_at.astimezone(timezone.utc).isoformat()
    return f"scan:{dev}:{iso}:{loc}".lower()


# ================================================================
# 请求模型
# ================================================================
class StockRecountRequest(BaseModel):
    item_id: int = Field(..., description="物料ID")
    location_id: int = Field(..., description="库位ID")
    actual: int = Field(..., description="实际数量")
    ctx: Dict[str, Any] | None = None


# ================================================================
# 事件写入（审计）
# ================================================================
async def _insert_event(
    session: AsyncSession, *, source: str, message: str, occurred_at: datetime
) -> int:
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


# ================================================================
# /stock/inventory/recount
# ================================================================
@router.post("/stock/inventory/recount")
async def stock_recount(
    req: StockRecountRequest,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    盘点某 item@location，使 qty = actual。
    注意：本接口属于“运维库存工具”，仍基于 (item_id,location_id) 维度，
    并不参与 scan 流程，不受 scan 架构变动影响。
    """
    device_id = (req.ctx or {}).get("device_id") if isinstance(req.ctx, dict) else None
    occurred_at = datetime.now(timezone.utc)

    # ★ 本地生成 scan_ref（替代 scan_utils.make_scan_ref）
    scan_ref = _make_scan_ref(device_id, occurred_at, req.location_id)

    try:
        from app.services.stock_service import StockService  # type: ignore
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"stock service missing: {e}")

    svc = StockService()

    async with session.begin():
        # 读取当前账面库存
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

        # 写 COUNT 差额账
        if delta != 0:
            await svc.adjust(
                session=session,
                item_id=int(req.item_id),
                location_id=int(req.location_id),
                delta=delta,
                reason="COUNT",
                ref=scan_ref,
            )

        ev_id = await _insert_event(
            session, source="stock_recount", message=scan_ref, occurred_at=occurred_at
        )

    return {
        "scan_ref": scan_ref,
        "event_id": ev_id,
        "on_hand": on_hand,
        "actual": int(req.actual),
        "delta": delta,
        "committed": True,
    }
