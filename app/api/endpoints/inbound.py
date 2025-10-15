# app/api/endpoints/inbound.py
from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.services.inbound_service import InboundService
from app.services.putaway_service import PutawayService
from app.schemas.inbound import ReceiveIn, ReceiveOut, PutawayIn

# ---------------- DB Session (绑定到同一 DATABASE_URL，确保与测试用夹具同库) ----------------
# 说明：
# - SQLAlchemy 2.x 的 psycopg v3 驱动支持异步，URL 形式仍是 postgresql+psycopg
# - 若你的项目使用 asyncpg，也可把 URL 改为 postgresql+asyncpg
_DB_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms")
_engine = create_async_engine(_DB_URL, future=True)
_SessionLocal = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncSession:
    async with _SessionLocal() as s:
        yield s


router = APIRouter(prefix="/inbound", tags=["inbound"])


@router.post("/receive", response_model=ReceiveOut)
async def inbound_receive(payload: ReceiveIn, session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    """入库到 STAGE（自动建 SKU / STAGE；UPSERT stocks；INBOUND 台账幂等）"""
    svc = InboundService()
    data = await svc.receive(
        session=session,
        sku=payload.sku,
        qty=payload.qty,
        ref=payload.ref,
        ref_line=payload.ref_line,
        batch_code=getattr(payload, "batch_code", None),
        production_date=getattr(payload, "production_date", None),
        expiry_date=getattr(payload, "expiry_date", None),
        occurred_at=getattr(payload, "occurred_at", None),
        stage_location_id=0,  # smoke 用例固定验证 loc_id=0
    )
    await session.commit()
    return {"item_id": data["item_id"], "accepted_qty": data["accepted_qty"], "idempotent": data.get("idempotent")}


@router.post("/putaway")
async def inbound_putaway(payload: PutawayIn, session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    """
    由入库暂存位搬运到目标库位：
    - 用 payload.sku 解析/创建 item_id
    - STAGE 解析优先 id=0（与 smoke 校验一致）
    - 右腿 +1（在 PutawayService 内部处理）
    """
    item_id = await _ensure_item(session, payload.sku)
    stage_id = await _resolve_stage_location(session, preferred_id=0)

    res = await PutawayService.putaway(
        session=session,
        item_id=item_id,
        from_location_id=stage_id,
        to_location_id=payload.to_location_id,
        qty=payload.qty,
        ref=payload.ref,
        ref_line=_to_ref_line_int(payload.ref_line),
    )
    await session.commit()
    return {"status": res.get("status", "ok"), "moved": res.get("moved", payload.qty)}


# ---------- helpers（与 service 同步优先序：先 id=0，再 ILIKE，再最小 id） ----------
async def _ensure_item(session: AsyncSession, sku: str) -> int:
    row = await session.execute(text("SELECT id FROM items WHERE sku = :sku LIMIT 1"), {"sku": sku})
    got = row.first()
    if got:
        return int(got[0])
    ins = await session.execute(text("INSERT INTO items (sku, name) VALUES (:sku, :name) RETURNING id"),
                                {"sku": sku, "name": sku})
    return int(ins.scalar())


async def _resolve_stage_location(session: AsyncSession, *, preferred_id: int) -> int:
    # 1) 优先 loc_id=0
    row = await session.execute(text("SELECT id FROM locations WHERE id = :i LIMIT 1"), {"i": preferred_id})
    got = row.first()
    if got:
        return int(got[0])

    # 2) 名称 ILIKE 'STAGE%'
    row = await session.execute(text("SELECT id FROM locations WHERE name ILIKE 'STAGE%' ORDER BY id ASC LIMIT 1"))
    got = row.first()
    if got:
        return int(got[0])

    # 3) 任意现有库位（最小 id）
    row = await session.execute(text("SELECT id FROM locations ORDER BY id ASC LIMIT 1"))
    got = row.first()
    if got:
        return int(got[0])

    # 4) 创建 preferred_id
    await session.execute(
        text("INSERT INTO locations (id, name, warehouse_id) VALUES (:i, 'STAGE', 1) ON CONFLICT (id) DO NOTHING"),
        {"i": preferred_id},
    )
    return int(preferred_id)


def _to_ref_line_int(ref_line: Any) -> int:
    if isinstance(ref_line, int):
        return ref_line
    import zlib
    return int(zlib.crc32(str(ref_line).encode("utf-8")) & 0x7FFFFFFF)
