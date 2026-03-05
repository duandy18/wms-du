# app/api/routers/orders_fulfillment_v2_routes_2_pick.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Set

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.lot_code_contract import (
    fetch_item_expiry_policy_map,
    validate_lot_code_contract,
)
from app.api.deps import get_session
from app.api.routers.orders_fulfillment_v2_helpers import get_order_ref_and_trace_id
from app.api.routers.orders_fulfillment_v2_schemas import PickRequest, PickResponse
from app.models.enums import MovementType
from app.services.pick_service import PickService


def _requires_batch_from_expiry_policy(v: object) -> bool:
    return str(v or "").upper() == "REQUIRED"


async def _load_actual_warehouse_id(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
) -> int | None:
    row = await session.execute(
        text(
            """
            SELECT f.actual_warehouse_id AS actual_warehouse_id
              FROM orders o
              LEFT JOIN order_fulfillment f ON f.order_id = o.id
             WHERE o.platform = :p
               AND o.shop_id  = :s
               AND o.ext_order_no = :o
             LIMIT 1
            """
        ),
        {"p": platform, "s": shop_id, "o": ext_order_no},
    )
    rec = row.mappings().first()
    if rec is None:
        return None
    aw = rec.get("actual_warehouse_id")
    return int(aw) if aw is not None else None


def register(router: APIRouter) -> None:
    @router.post(
        "/{platform}/{shop_id}/{ext_order_no}/pick",
        response_model=List[PickResponse],
    )
    async def order_pick(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        body: PickRequest,
        session: AsyncSession = Depends(get_session),
    ):
        plat = platform.upper()

        if not body.lines:
            return []

        item_ids: Set[int] = {int(ln.item_id) for ln in body.lines}
        expiry_policy_map = await fetch_item_expiry_policy_map(session, item_ids)

        missing_items = [str(i) for i in sorted(item_ids) if i not in expiry_policy_map]
        if missing_items:
            raise HTTPException(status_code=422, detail=f"unknown item_id(s): {', '.join(missing_items)}")

        order_ref, trace_id = await get_order_ref_and_trace_id(
            session=session,
            platform=plat,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
        )

        actual_wh = await _load_actual_warehouse_id(
            session,
            platform=plat,
            shop_id=str(shop_id),
            ext_order_no=str(ext_order_no),
        )
        if actual_wh is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PICK_WAREHOUSE_NOT_ASSIGNED",
                    "message": "订单尚未绑定执行仓（order_fulfillment.actual_warehouse_id 为空），禁止拣货；请先手工指定执行仓。",
                    "order_ref": order_ref,
                    "trace_id": trace_id,
                },
            )

        requested_wh = int(body.warehouse_id)
        if requested_wh != int(actual_wh):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PICK_WAREHOUSE_CONFLICT",
                    "message": "执行仓冲突：以 order_fulfillment.actual_warehouse_id 为准。",
                    "order_ref": order_ref,
                    "trace_id": trace_id,
                    "existing_actual_warehouse_id": int(actual_wh),
                    "incoming_warehouse_id": int(requested_wh),
                },
            )

        svc = PickService()
        occurred_at = body.occurred_at or datetime.now(timezone.utc)

        responses: List[PickResponse] = []
        ref_line = 1

        try:
            for line in body.lines:
                requires_batch = _requires_batch_from_expiry_policy(expiry_policy_map.get(int(line.item_id)))

                bc = validate_lot_code_contract(
                    requires_batch=requires_batch,
                    lot_code=getattr(line, "batch_code", None),
                )

                result = await svc.record_pick(
                    session=session,
                    item_id=line.item_id,
                    qty=line.qty,
                    ref=order_ref,
                    occurred_at=occurred_at,
                    batch_code=bc,
                    warehouse_id=requested_wh,
                    trace_id=trace_id,
                    start_ref_line=ref_line,
                    movement_type=MovementType.SHIP,
                )
                ref_line = int(result.get("ref_line", ref_line)) + 1

                responses.append(
                    PickResponse(
                        item_id=line.item_id,
                        warehouse_id=result.get("warehouse_id", requested_wh),
                        batch_code=result.get("batch_code", bc),
                        picked=result.get("picked", line.qty),
                        stock_after=result.get("stock_after"),
                        ref=result.get("ref", order_ref),
                        status=result.get("status", "OK"),
                    )
                )

            await session.commit()

        except ValueError as e:
            await session.rollback()
            raise HTTPException(409, detail=str(e)) from e
        except Exception:
            await session.rollback()
            raise

        return responses
