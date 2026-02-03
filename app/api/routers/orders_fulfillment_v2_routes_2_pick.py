# app/api/routers/orders_fulfillment_v2_routes_2_pick.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Set

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.batch_code_contract import fetch_item_has_shelf_life_map, validate_batch_code_contract
from app.api.deps import get_session
from app.api.routers.orders_fulfillment_v2_helpers import get_order_ref_and_trace_id
from app.api.routers.orders_fulfillment_v2_schemas import PickRequest, PickResponse
from app.models.enums import MovementType
from app.services.pick_service import PickService


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

        # ✅ 主线 A：API 合同收紧（422 拦假码）
        item_ids: Set[int] = {int(ln.item_id) for ln in body.lines}
        has_shelf_life_map = await fetch_item_has_shelf_life_map(session, item_ids)

        missing_items = [str(i) for i in sorted(item_ids) if i not in has_shelf_life_map]
        if missing_items:
            raise HTTPException(status_code=422, detail=f"unknown item_id(s): {', '.join(missing_items)}")

        any_requires = any(has_shelf_life_map.get(i, False) is True for i in item_ids)
        any_not_requires = any(has_shelf_life_map.get(i, False) is not True for i in item_ids)

        # 由于该接口只有一个 body.batch_code，无法同时满足“批次必填”和“非批次必须为 null”
        if any_requires and any_not_requires:
            raise HTTPException(
                status_code=422,
                detail=(
                    "mixed items detected (has_shelf_life true and not true). "
                    "This endpoint requires per-line batch_code; single body.batch_code is not allowed for mixed orders."
                ),
            )

        batch_code = validate_batch_code_contract(requires_batch=any_requires, batch_code=getattr(body, "batch_code", None))

        order_ref, trace_id = await get_order_ref_and_trace_id(
            session=session,
            platform=plat,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
        )

        svc = PickService()
        occurred_at = body.occurred_at or datetime.now(timezone.utc)

        responses: List[PickResponse] = []
        ref_line = 1

        try:
            for line in body.lines:
                result = await svc.record_pick(
                    session=session,
                    item_id=line.item_id,
                    qty=line.qty,
                    ref=order_ref,
                    occurred_at=occurred_at,
                    batch_code=batch_code,
                    warehouse_id=body.warehouse_id,
                    trace_id=trace_id,
                    start_ref_line=ref_line,
                    # ✅ 关键修复：订单出库扣减必须记为 SHIPMENT（而不是 ADJUSTMENT）
                    movement_type=MovementType.SHIP,
                )
                ref_line = result.get("ref_line", ref_line) + 1

                responses.append(
                    PickResponse(
                        item_id=line.item_id,
                        warehouse_id=result.get("warehouse_id", body.warehouse_id),
                        batch_code=result.get("batch_code", batch_code),
                        picked=result.get("picked", line.qty),
                        stock_after=result.get("stock_after"),
                        ref=result.get("ref", order_ref),
                        status=result.get("status", "OK"),
                    )
                )

            await session.commit()

        except ValueError as e:
            await session.rollback()
            raise HTTPException(409, detail=str(e))
        except Exception:
            await session.rollback()
            raise

        return responses
