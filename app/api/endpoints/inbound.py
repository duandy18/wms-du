# app/api/endpoints/inbound.py
from __future__ import annotations

from datetime import UTC
from datetime import date as _date
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 导出可覆盖依赖符号（tests 会覆盖此对象）
from app.db.session import get_session as _project_get_session
from app.schemas.inbound import PutawayIn, ReceiveIn, ReceiveOut
from app.services.inbound_service import InboundService
from app.services.putaway_service import PutawayService


async def get_session() -> AsyncSession:
    async for s in _project_get_session():
        yield s


router = APIRouter(prefix="/inbound", tags=["inbound"])

# ---------------- Helpers ----------------


async def _ensure_item(session: AsyncSession, sku: str) -> int:
    row = await session.execute(text("SELECT id FROM items WHERE sku = :sku LIMIT 1"), {"sku": sku})
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
        text("SELECT id FROM locations WHERE id = :i LIMIT 1"), {"i": preferred_id}
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
            "INSERT INTO locations (id, name, warehouse_id) VALUES (:i, 'STAGE', 1) ON CONFLICT (id) DO NOTHING"
        ),
        {"i": preferred_id},
    )
    return int(preferred_id)


def _to_ref_line_int(ref_line: Any) -> int:
    if isinstance(ref_line, int):
        return ref_line
    import zlib

    return int(zlib.crc32(str(ref_line).encode("utf-8")) & 0x7FFFFFFF)


async def _batches_exists(session: AsyncSession) -> bool:
    r = await session.execute(text("SELECT to_regclass('public.batches') IS NOT NULL"))
    return bool(r.scalar())


async def _batch_conflict(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    location_id: int,
    batch_code: str | None,
    production_date: _date | None,
    expiry_date: _date | None,
) -> bool:
    if not batch_code:
        return False
    if not await _batches_exists(session):
        return False
    row = await session.execute(
        text(
            """
            SELECT 1
            FROM public.batches
            WHERE item_id=:item AND warehouse_id=:wh AND location_id=:loc AND batch_code=:code
              AND (production_date IS DISTINCT FROM :pd OR expiry_date IS DISTINCT FROM :ed)
            LIMIT 1
        """
        ),
        {
            "item": item_id,
            "wh": warehouse_id,
            "loc": location_id,
            "code": batch_code,
            "pd": production_date,
            "ed": expiry_date,
        },
    )
    return row.first() is not None


async def _batch_upsert_once(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    location_id: int,
    batch_code: str | None,
    production_date: _date | None,
    expiry_date: _date | None,
) -> None:
    if not batch_code or not await _batches_exists(session):
        return
    await session.execute(
        text(
            """
            INSERT INTO public.batches
                (item_id, warehouse_id, location_id, batch_code, production_date, expiry_date, qty)
            VALUES (:item, :wh, :loc, :code, :pd, :ed, 0)
            ON CONFLICT (item_id, warehouse_id, location_id, batch_code, production_date, expiry_date)
            DO NOTHING
        """
        ),
        {
            "item": item_id,
            "wh": warehouse_id,
            "loc": location_id,
            "code": batch_code,
            "pd": production_date,
            "ed": expiry_date,
        },
    )


# ---------------- Endpoints ----------------


@router.post("/receive", response_model=ReceiveOut)
async def inbound_receive(
    payload: ReceiveIn, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    item_id = await _ensure_item(session, payload.sku)
    stage_id = await _resolve_stage_location(session, preferred_id=0)

    # 422：同批次不同效期
    pd = payload.production_date if isinstance(payload.production_date, _date) else None
    ed = payload.expiry_date if isinstance(payload.expiry_date, _date) else None
    if await _batch_conflict(
        session,
        item_id=item_id,
        warehouse_id=1,
        location_id=stage_id,
        batch_code=getattr(payload, "batch_code", None),
        production_date=pd,
        expiry_date=ed,
    ):
        raise HTTPException(status_code=422, detail="BATCH_EXPIRY_CONFLICT")

    await _batch_upsert_once(
        session,
        item_id=item_id,
        warehouse_id=1,
        location_id=stage_id,
        batch_code=getattr(payload, "batch_code", None),
        production_date=pd,
        expiry_date=ed,
    )

    svc = InboundService()
    data = await svc.receive(
        session=session,
        sku=payload.sku,
        qty=payload.qty,
        ref=payload.ref,
        ref_line=payload.ref_line,
        batch_code=getattr(payload, "batch_code", None),
        production_date=payload.production_date,
        expiry_date=payload.expiry_date,
        occurred_at=getattr(payload, "occurred_at", None),
        stage_location_id=0,
    )
    await session.commit()

    # 幂等第二次 → 409
    if data.get("idempotent") is True:
        raise HTTPException(status_code=409, detail="IDEMPOTENT")

    return {
        "item_id": data["item_id"],
        "accepted_qty": data["accepted_qty"],
        "idempotent": data.get("idempotent"),
    }


@router.post("/putaway")
async def inbound_putaway(
    payload: PutawayIn, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    item_id = await _ensure_item(session, payload.sku)
    stage_id = await _resolve_stage_location(session, preferred_id=0)
    try:
        res = await PutawayService.putaway(
            session=session,
            item_id=item_id,
            from_location_id=stage_id,
            to_location_id=payload.to_location_id,
            qty=payload.qty,
            ref=payload.ref,
            ref_line=_to_ref_line_int(payload.ref_line),
            occurred_at=datetime.now(UTC),
        )
        await session.commit()
    except ValueError:
        # 负库存/不足量
        raise HTTPException(status_code=409, detail="NEGATIVE_STOCK")
    return {"status": res.get("status", "ok"), "moved": res.get("moved", payload.qty)}


@router.post("/scan")
async def inbound_scan(
    payload: dict[str, Any], session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    code = payload.get("barcode")
    # smoke 期望 detail 是固定枚举
    if not isinstance(code, str) or not code.isdigit():
        raise HTTPException(status_code=400, detail="INVALID_BARCODE")
    return {"ok": True}
