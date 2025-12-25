# app/api/routers/shipping_records_routes_read.py
from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.routers.shipping_records_schemas import ShippingRecordOut


def register(router: APIRouter) -> None:
    @router.get(
        "/shipping-records/{record_id}",
        response_model=ShippingRecordOut,
        summary="按 ID 查询单条发货账本记录",
    )
    async def get_shipping_record_by_id(
        record_id: int,
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> ShippingRecordOut:
        sql = text(
            """
            SELECT
              id,
              order_ref,
              platform,
              shop_id,
              warehouse_id,
              carrier_code,
              carrier_name,
              tracking_no,
              trace_id,
              weight_kg,
              gross_weight_kg,
              packaging_weight_kg,
              cost_estimated,
              cost_real,
              delivery_time,
              status,
              error_code,
              error_message,
              meta,
              created_at
            FROM shipping_records
            WHERE id = :id
            """
        )
        row = (await session.execute(sql, {"id": record_id})).mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="shipping_record not found")
        return ShippingRecordOut(**dict(row))

    @router.get(
        "/shipping-records/by-ref/{order_ref}",
        response_model=List[ShippingRecordOut],
        summary="按订单引用（order_ref）查询发货账本记录（可能多条）",
    )
    async def get_shipping_records_by_ref(
        order_ref: str,
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> List[ShippingRecordOut]:
        sql = text(
            """
            SELECT
              id,
              order_ref,
              platform,
              shop_id,
              warehouse_id,
              carrier_code,
              carrier_name,
              tracking_no,
              trace_id,
              weight_kg,
              gross_weight_kg,
              packaging_weight_kg,
              cost_estimated,
              cost_real,
              delivery_time,
              status,
              error_code,
              error_message,
              meta,
              created_at
            FROM shipping_records
            WHERE order_ref = :order_ref
            ORDER BY created_at DESC, id DESC
            """
        )
        result = await session.execute(sql, {"order_ref": order_ref})
        rows = result.mappings().all()
        return [ShippingRecordOut(**dict(r)) for r in rows]
