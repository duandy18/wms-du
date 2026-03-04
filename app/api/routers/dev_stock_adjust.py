# app/api/routers/dev_stock_adjust.py
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.lot_code_contract import fetch_item_expiry_policy_map, validate_lot_code_contract
from app.models.enums import MovementType
from app.services.stock.lots import ensure_lot_full
from app.services.stock_service import StockService

router = APIRouter(prefix="/dev", tags=["dev-stock"])


class DevStockAdjustIn(BaseModel):
    warehouse_id: int = Field(..., ge=1)
    item_id: int = Field(..., ge=1)
    delta: int = Field(..., description="库存变化量，正数=加库存，负数=减库存")
    batch_code: Optional[str] = None

    reason: str = Field(default=str(MovementType.RECEIPT))
    ref: str = Field(default="dev:stock_adjust")
    ref_line: int = Field(default=1, ge=1)

    occurred_at: Optional[datetime] = None
    production_date: Optional[date] = None
    expiry_date: Optional[date] = None


async def _ensure_supplier_lot(session: AsyncSession, *, wh_id: int, item_id: int, lot_code: str) -> int:
    """
    Phase 2：SUPPLIER lot upsert 入口收口到 ensure_lot_full（唯一写 lots 的入口）。
    lots 不承载日期事实；仅结构身份 + 必要快照。
    """
    try:
        return await ensure_lot_full(
            session,
            item_id=int(item_id),
            warehouse_id=int(wh_id),
            lot_code=str(lot_code),
            production_date=None,
            expiry_date=None,
        )
    except ValueError as e:
        # ensure_lot_full 对空 lot_code 会 ValueError
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"failed to ensure SUPPLIER lot for item_id={item_id}: {e}") from e


async def _create_internal_lot(session: AsyncSession, *, wh_id: int, item_id: int, ref: str) -> int:
    """
    INTERNAL lot 必须满足 source_receipt_id/source_line_no NOT NULL（DB check）。
    这里创建一个最小 inbound_receipts 来承载来源。
    """
    r = await session.execute(
        SA(
            """
            INSERT INTO inbound_receipts (
                warehouse_id, source_type, source_id, ref, trace_id, status, remark, occurred_at, created_at, updated_at
            )
            VALUES (
                :wh, 'PO', NULL, :ref, NULL, 'DRAFT', 'dev internal lot source receipt', :occurred_at, now(), now()
            )
            RETURNING id
            """
        ),
        {"wh": int(wh_id), "ref": str(ref), "occurred_at": datetime.now(timezone.utc)},
    )
    receipt_id = int(r.scalar_one())

    r2 = await session.execute(
        SA(
            """
            INSERT INTO lots (
                warehouse_id,
                item_id,
                lot_code_source,
                lot_code,
                source_receipt_id,
                source_line_no,
                created_at,
                item_shelf_life_value_snapshot,
                item_shelf_life_unit_snapshot,
                item_lot_source_policy_snapshot,
                item_expiry_policy_snapshot,
                item_derivation_allowed_snapshot,
                item_uom_governance_enabled_snapshot
            )
            SELECT
                :wh,
                it.id,
                'INTERNAL',
                NULL,
                :rid,
                1,
                now(),
                it.shelf_life_value,
                it.shelf_life_unit,
                it.lot_source_policy,
                it.expiry_policy,
                it.derivation_allowed,
                it.uom_governance_enabled
            FROM items it
            WHERE it.id = :i
            RETURNING id
            """
        ),
        {"wh": int(wh_id), "i": int(item_id), "rid": int(receipt_id)},
    )
    return int(r2.scalar_one())


async def _pick_any_internal_lot_with_stock(session: AsyncSession, *, wh_id: int, item_id: int) -> Optional[int]:
    """
    当 batch_code=None 且 delta<0 时，优先从已有库存中挑一个 INTERNAL lot 扣减，避免凭空造 lot。
    """
    row = (
        await session.execute(
            SA(
                """
                SELECT s.lot_id
                  FROM stocks_lot s
                  JOIN lots lo
                    ON lo.id = s.lot_id
                   AND lo.warehouse_id = s.warehouse_id
                   AND lo.item_id = s.item_id
                 WHERE s.warehouse_id = :w
                   AND s.item_id      = :i
                   AND lo.lot_code IS NULL
                   AND s.qty > 0
                 ORDER BY s.lot_id ASC
                 LIMIT 1
                """
            ),
            {"w": int(wh_id), "i": int(item_id)},
        )
    ).first()
    return int(row[0]) if row else None


@router.post("/stock/adjust")
async def dev_stock_adjust(
    payload: DevStockAdjustIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    # 合同：batch_code(展示码/旧名) 对 expiry-policy REQUIRED 的商品必须合法；对 NONE 必须为 null
    pol_map = await fetch_item_expiry_policy_map(session, {int(payload.item_id)})
    if int(payload.item_id) not in pol_map:
        raise HTTPException(status_code=422, detail=f"unknown item_id: {payload.item_id}")

    requires_batch = str(pol_map[int(payload.item_id)]).upper() == "REQUIRED"
    norm_batch = validate_lot_code_contract(requires_batch=requires_batch, lot_code=payload.batch_code)

    # 对 REQUIRED 商品：正向入库/加库存时，必须提供日期（让库存引擎能记 receipt 日期事实）
    if requires_batch and int(payload.delta) > 0:
        if payload.production_date is None or payload.expiry_date is None:
            raise HTTPException(
                status_code=422,
                detail="production_date and expiry_date are required for expiry-policy REQUIRED items when delta > 0",
            )

    ts = payload.occurred_at or datetime.now(timezone.utc)

    # Lot-World 终态：必须落到真实 lot_id
    if norm_batch:
        lot_id = await _ensure_supplier_lot(
            session,
            wh_id=int(payload.warehouse_id),
            item_id=int(payload.item_id),
            lot_code=str(norm_batch),
        )
    else:
        # batch_code=None：优先从现有库存选 INTERNAL lot；否则创建一个新的 INTERNAL lot
        lot_id = await _pick_any_internal_lot_with_stock(session, wh_id=int(payload.warehouse_id), item_id=int(payload.item_id))
        if lot_id is None:
            lot_id = await _create_internal_lot(
                session,
                wh_id=int(payload.warehouse_id),
                item_id=int(payload.item_id),
                ref=str(payload.ref),
            )

    svc = StockService()
    try:
        res = await svc.adjust_lot(
            session=session,
            item_id=int(payload.item_id),
            warehouse_id=int(payload.warehouse_id),
            lot_id=int(lot_id),
            delta=int(payload.delta),
            reason=str(payload.reason),
            ref=str(payload.ref),
            ref_line=int(payload.ref_line),
            occurred_at=ts,
            batch_code=norm_batch,
            production_date=payload.production_date,
            expiry_date=payload.expiry_date,
            trace_id="dev-stock-adjust",
        )
        await session.commit()
        return {"ok": True, "result": res}
    except Exception:
        await session.rollback()
        raise
