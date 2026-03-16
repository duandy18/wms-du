# app/tms/records/routes_read.py
#
# 分拆说明：
# - 本文件承载 TMS / Records（物流台帐）只读路由；
# - 保持既有 URL 与 response contract 不变，仅完成物理归属收口；
# - 具体 SQL 下沉到 repository，避免 router 内直接承载查询实现。
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.tms.records.contracts import ShippingRecordOut
from app.tms.records.repository import (
    get_shipping_record_by_id,
    list_shipping_records_by_order_ref,
)


def register(router: APIRouter) -> None:
    @router.get(
        "/shipping-records/{record_id}",
        response_model=ShippingRecordOut,
        summary="按 ID 查询单条物流台帐记录",
    )
    async def get_shipping_record_by_id_route(
        record_id: int,
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> ShippingRecordOut:
        del current_user

        row = await get_shipping_record_by_id(session=session, record_id=record_id)
        if row is None:
            raise HTTPException(status_code=404, detail="shipping_record not found")
        return ShippingRecordOut(**row)

    @router.get(
        "/shipping-records/by-ref/{order_ref}",
        response_model=list[ShippingRecordOut],
        summary="按订单引用（order_ref）查询物流台帐记录（可能多条）",
    )
    async def get_shipping_records_by_ref_route(
        order_ref: str,
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> list[ShippingRecordOut]:
        del current_user

        rows = await list_shipping_records_by_order_ref(session=session, order_ref=order_ref)
        return [ShippingRecordOut(**row) for row in rows]
