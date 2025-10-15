# app/api/endpoints/inbound.py
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inbound_service import InboundService
from app.services.putaway_service import PutawayService
from app.schemas.inbound import ReceiveIn, ReceiveOut, PutawayIn

# 关键：导出本模块“同名依赖函数”以便 tests 覆盖
from app.db.session import get_session as _project_get_session

async def get_session() -> AsyncSession:
    """
    本模块导出的依赖符号。
    默认桥接到项目原生 get_session；tests 可用
        app.dependency_overrides[app.api.endpoints.inbound.get_session] = async_session_maker
    覆盖到同一函数对象，从而与断言共享同一 Engine/事务域。
    """
    async for s in _project_get_session():
        yield s


router = APIRouter(prefix="/inbound", tags=["inbound"])


@router.post("/receive", response_model=ReceiveOut)
async def inbound_receive(
    payload: ReceiveIn,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
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
        stage_location_id=0,  # smoke 断言 loc_id=0
    )
    await session.commit()
    return {
        "item_id": data["item_id"],
        "accepted_qty": data["accepted_qty"],
        "idempotent": data.get("idempotent"),
    }


@router.post("/putaway")
async def inbound_putaway(
    payload: PutawayIn,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    # 解析/创建 item
    item_id = await _ensure_item(session, payload.sku)
    # 优先使用 0 号 STAGE
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


# ---------- helpers ----------
async def _ensure_item(session: AsyncSession, sku: str) -> int:
    row = await session.execute(
        text("SELECT id FROM items WHERE sku = :sku LIMIT 1"),
        {"sku": sku},
    )
    got = row.first()
    if got:
        return int(got[0])
    ins = await session.execute(
        text("INSERT INTO items (sku, name) VALUES (:sku, :name) RETURNING id"),
        {"sku": sku, "name": sku},
    )
    return int(ins.scalar())


async def _resolve_stage_location(session: AsyncSession, *, preferred_id: int) -> int:
    row = await session.execute(
        text("SELECT id FROM locations WHERE id = :i LIMIT 1"),
        {"i": preferred_id},
    )
    got = row.first()
    if got:
        return int(got[0])

    row = await session.execute(
        text("SELECT id FROM locations WHERE name ILIKE 'STAGE%' ORDER BY id ASC LIMIT 1")
    )
    got = row.first()
    if got:
        return int(got[0])

    row = await session.execute(text("SELECT id FROM locations ORDER BY id ASC LIMIT 1"))
    got = row.first()
    if got:
        return int(got[0])

    await session.execute(
        text(
            "INSERT INTO locations (id, name, warehouse_id) "
            "VALUES (:i, 'STAGE', 1) ON CONFLICT (id) DO NOTHING"
        ),
        {"i": preferred_id},
    )
    return int(preferred_id)


def _to_ref_line_int(ref_line: Any) -> int:
    if isinstance(ref_line, int):
        return ref_line
    import zlib
    return int(zlib.crc32(str(ref_line).encode("utf-8")) & 0x7FFFFFFF)
