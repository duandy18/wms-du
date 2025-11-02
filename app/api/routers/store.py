# app/api/routers/store.py
from __future__ import annotations

from typing import Optional, Sequence
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import get_async_session
from app.services.store_service import StoreService
from app.services.channel_inventory_service import ChannelInventoryService

try:
    from app.config.flags import ENABLE_PDD_PUSH  # 可选开关
except Exception:
    ENABLE_PDD_PUSH = False

router = APIRouter(prefix="/stores", tags=["stores"])


class RefreshRequest(BaseModel):
    item_ids: Optional[Sequence[int]] = Field(default=None, description="只刷新这些 item_id；None 表示全部绑定")
    dry_run: bool = Field(default=False, description="True 仅计算；False 落表到 channel_inventory.visible_qty")


@router.post("/{store_id}/refresh")
async def refresh_store_inventory(
    store_id: int,
    body: RefreshRequest,
    session: AsyncSession = Depends(get_async_session),
):
    try:
        res = await StoreService.refresh_channel_inventory_for_store(
            session, store_id=store_id, item_ids=body.item_ids, dry_run=body.dry_run
        )
        return {"ok": True, **res}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{store_id}/visible")
async def get_store_visible(
    store_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    res = await StoreService.refresh_channel_inventory_for_store(
        session, store_id=store_id, item_ids=None, dry_run=True
    )
    return {"ok": True, "store_id": store_id, "items": res["items"]}


class ReserveRequest(BaseModel):
    item_id: int
    qty: int = Field(ge=1, description="本次占用数量（正数）")
    ext_order_id: str = Field(min_length=1, max_length=64)
    ext_sku_id: str = Field(min_length=1, max_length=64)
    op: str = Field(default="RESERVE", description="幂等操作类型，默认 RESERVE")
    refresh_visible: bool = True


@router.post("/{store_id}/reserve")
async def reserve_for_store(
    store_id: int,
    body: ReserveRequest,
    session: AsyncSession = Depends(get_async_session),
):
    try:
        # 幂等落库
        res = await session.execute(
            text("""
                INSERT INTO channel_reserve_ops (store_id, ext_order_id, ext_sku_id, op, qty)
                VALUES (:sid, :oid, :sk, :op, :qty)
                ON CONFLICT ON CONSTRAINT uq_reserve_idem_key DO NOTHING
                RETURNING id
            """),
            {"sid": store_id, "oid": body.ext_order_id, "sk": body.ext_sku_id, "op": body.op, "qty": body.qty},
        )
        inserted_id = res.scalar_one_or_none()
        if inserted_id is None:
            current_reserved = await _get_reserved(session, store_id, body.item_id)
            return {
                "ok": True,
                "idempotent": True,
                "store_id": store_id,
                "item_id": body.item_id,
                "reserved_qty": current_reserved,
                "visible_refreshed": False,
            }

        new_reserved = await ChannelInventoryService.adjust_reserved(
            session, store_id=store_id, item_id=body.item_id, delta=body.qty
        )
        if body.refresh_visible:
            await StoreService.refresh_channel_inventory_for_store(
                session, store_id=store_id, item_ids=[body.item_id], dry_run=False
            )
        return {
            "ok": True,
            "idempotent": False,
            "store_id": store_id,
            "item_id": body.item_id,
            "reserved_qty": new_reserved,
            "visible_refreshed": body.refresh_visible,
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


async def _get_reserved(session: AsyncSession, store_id: int, item_id: int) -> int:
    row = await session.execute(
        text("SELECT reserved_qty FROM channel_inventory WHERE store_id=:sid AND item_id=:iid"),
        {"sid": store_id, "iid": item_id},
    )
    v = row.scalar_one_or_none()
    return int(v or 0)


@router.post("/{store_id}/pdd/push", status_code=501)
async def push_store_visible_preview(
    store_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    res = await StoreService.refresh_channel_inventory_for_store(
        session, store_id=store_id, item_ids=None, dry_run=True
    )
    payload = [{"item_id": x["item_id"], "qty": x["visible"]} for x in res["items"]]
    return {
        "ok": False,
        "reason": "Not Implemented (shadow mode)",
        "preview": {"store_id": store_id, "items": payload},
        "note": ("ENABLE_PDD_PUSH is off" if not ENABLE_PDD_PUSH else "PUSH gated by adapter wiring"),
    }
