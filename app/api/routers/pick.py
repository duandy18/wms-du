# app/api/routers/pick.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Set

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.lot_code_contract import fetch_item_expiry_policy_map, validate_lot_code_contract
from app.api.problem import raise_409, raise_422
from app.db.session import get_session
from app.services.pick_service import PickService

router = APIRouter(prefix="/pick", tags=["pick"])


def _requires_batch_from_expiry_policy(v: object) -> bool:
    return str(v or "").upper() == "REQUIRED"


class PickIn(BaseModel):
    item_id: int = Field(..., ge=1)
    qty: int = Field(..., ge=1)
    warehouse_id: int = Field(..., ge=1)

    lot_code: Optional[str] = Field(default=None, description="Lot 展示码（优先使用；等价于 batch_code）")
    batch_code: Optional[str] = None

    ref: str = Field(..., min_length=1)
    occurred_at: Optional[datetime] = None

    task_line_id: Optional[int] = None
    # ❌ legacy_location 已彻底移除（不兼容、不保留）
    device_id: Optional[str] = None
    operator: Optional[str] = None


class PickOut(BaseModel):
    item_id: int
    warehouse_id: int
    lot_code: Optional[str] = None
    batch_code: Optional[str] = None
    picked: int
    stock_after: Optional[int] = None
    ref: str
    status: str


@router.post("", response_model=PickOut)
async def pick_commit(
    body: PickIn,
    session: AsyncSession = Depends(get_session),
):
    svc = PickService()
    occurred_at = body.occurred_at or datetime.now(timezone.utc)

    item_ids: Set[int] = {int(body.item_id)}
    expiry_policy_map = await fetch_item_expiry_policy_map(session, item_ids)

    if body.item_id not in expiry_policy_map:
        raise_422(
            "unknown_item",
            f"未知商品 item_id={body.item_id}。",
            details=[{"type": "validation", "path": "item_id", "item_id": int(body.item_id), "reason": "unknown"}],
        )

    requires_batch = _requires_batch_from_expiry_policy(expiry_policy_map.get(body.item_id))

    lot_code = body.lot_code or body.batch_code
    batch_code = validate_lot_code_contract(
        requires_batch=requires_batch,
        lot_code=lot_code,
    )

    try:
        result = await svc.record_pick(
            session=session,
            item_id=body.item_id,
            qty=body.qty,
            ref=body.ref,
            occurred_at=occurred_at,
            batch_code=batch_code,
            warehouse_id=body.warehouse_id,
            trace_id=None,
            start_ref_line=1,
        )
        await session.commit()
    except ValueError as e:
        await session.rollback()
        raise_409(
            "pick_commit_reject",
            str(e),
            details=[{"type": "business", "path": "pick", "reason": str(e)}],
        )
    except Exception:
        await session.rollback()
        raise

    out_code = result.get("batch_code", batch_code)
    return PickOut(
        item_id=body.item_id,
        warehouse_id=result.get("warehouse_id", body.warehouse_id),
        lot_code=out_code,
        batch_code=out_code,
        picked=result.get("picked", body.qty),
        stock_after=result.get("stock_after"),
        ref=result.get("ref", body.ref),
        status=result.get("status", "OK"),
    )
