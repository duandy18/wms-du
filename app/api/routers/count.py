# app/api/routers/count.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.scan_utils import parse_barcode, make_scan_ref

router = APIRouter()


class CountRequest(BaseModel):
    """按库位/物料进行盘点：传入实际数量(actual)。"""
    tokens: Dict[str, Any] | None = None      # 支持 tokens.barcode 自动补齐
    ctx: Dict[str, Any] | None = None
    probe: bool = False

    item_id: Optional[int] = Field(None, description="物料ID")
    location_id: Optional[int] = Field(None, description="库位ID")
    qty: Optional[int] = Field(None, description="实际数量 (actual)")

    @model_validator(mode="after")
    def autofill_from_barcode(self) -> "CountRequest":
        if isinstance(self.tokens, dict):
            bc = self.tokens.get("barcode")
            if isinstance(bc, str) and bc.strip():
                parsed = parse_barcode(bc)
                if self.item_id is None:
                    self.item_id = parsed.get("item_id")
                if self.location_id is None:
                    self.location_id = parsed.get("location_id")
                if self.qty is None:
                    self.qty = parsed.get("qty")
        return self


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


@router.post("/count")
async def count_inventory(req: CountRequest, session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    """按差额落账（COUNT）：delta = actual - on_hand；delta!=0 时写一条账页（理由 COUNT）。"""
    device_id = (req.ctx or {}).get("device_id") if isinstance(req.ctx, dict) else None
    occurred_at = datetime.now(timezone.utc)

    if req.item_id is None or req.location_id is None or req.qty is None:
        raise HTTPException(status_code=400, detail="count requires ITEM, LOC, QTY(actual)")

    scan_ref = make_scan_ref(device_id, occurred_at, req.location_id)

    # 仅记录探测事件
    if req.probe:
        async with session.begin():
            ev_id = await _insert_event(session, source="count_probe", message=scan_ref, occurred_at=occurred_at)
        return {
            "scan_ref": scan_ref,
            "source": "count_probe",
            "occurred_at": occurred_at.isoformat(),
            "committed": False,
            "event_id": ev_id,
            "result": {"hint": "count probe"},
        }

    # 计算差额 → adjust 一条 COUNT 账
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
        delta = int(req.qty) - on_hand

        if delta != 0:
            await svc.adjust(
                session=session,
                item_id=int(req.item_id),
                location_id=int(req.location_id),
                delta=delta,
                reason="COUNT",
                ref=scan_ref,
            )

        ev_id = await _insert_event(session, source="count_commit", message=scan_ref, occurred_at=occurred_at)

    return {
        "scan_ref": scan_ref,
        "source": "count_commit",
        "occurred_at": occurred_at.isoformat(),
        "committed": True,
        "event_id": ev_id,
        "result": {"on_hand": on_hand, "counted": int(req.qty), "delta": delta},
    }
