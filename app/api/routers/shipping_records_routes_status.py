# app/api/routers/shipping_records_routes_status.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.routers.shipping_records_schemas import ShippingStatusUpdateIn, ShippingStatusUpdateOut
from app.services.audit_writer import AuditEventWriter


def register(router: APIRouter) -> None:
    @router.post(
        "/shipping-records/{record_id}/status",
        response_model=ShippingStatusUpdateOut,
        summary="更新单条发货账本的状态 / delivery_time",
        status_code=status.HTTP_200_OK,
    )
    async def update_shipping_record_status(
        record_id: int,
        payload: ShippingStatusUpdateIn,
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> ShippingStatusUpdateOut:
        # 1) 查当前记录
        select_sql = text(
            """
            SELECT
              id,
              order_ref,
              trace_id,
              status,
              delivery_time,
              error_code,
              error_message,
              meta
            FROM shipping_records
            WHERE id = :id
            """
        )
        row = (await session.execute(select_sql, {"id": record_id})).mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="shipping_record not found")

        order_ref = str(row["order_ref"])
        trace_id = row.get("trace_id")
        old_status = row.get("status")
        old_delivery_time = row.get("delivery_time")
        old_meta = row.get("meta") or {}
        old_error_code = row.get("error_code")
        old_error_message = row.get("error_message")

        # 2) delivery_time
        if payload.delivery_time is not None:
            new_delivery_time = payload.delivery_time
        elif payload.status == "DELIVERED" and old_delivery_time is None:
            new_delivery_time = datetime.now(timezone.utc)
        else:
            new_delivery_time = old_delivery_time

        # 3) merge meta
        new_meta = dict(old_meta)
        if payload.meta:
            new_meta.update(payload.meta)
        if payload.error_code is not None:
            new_meta["error_code"] = payload.error_code
        if payload.error_message is not None:
            new_meta["error_message"] = payload.error_message

        json_meta = json.dumps(new_meta, ensure_ascii=False) if new_meta else None

        # 4) update（meta 强制写 jsonb）
        update_sql = text(
            """
            UPDATE shipping_records
               SET status = :status,
                   delivery_time = :delivery_time,
                   error_code = :error_code,
                   error_message = :error_message,
                   meta = CAST(:meta AS jsonb)
             WHERE id = :id
            """
        )
        await session.execute(
            update_sql,
            {
                "id": record_id,
                "status": payload.status,
                "delivery_time": new_delivery_time,
                "error_code": payload.error_code,
                "error_message": payload.error_message,
                "meta": json_meta,
            },
        )

        # 5) audit
        try:
            await AuditEventWriter.write(
                session,
                flow="OUTBOUND",
                event="SHIP_STATUS_UPDATE",
                ref=order_ref,
                trace_id=trace_id,
                meta={
                    "old_status": old_status,
                    "new_status": payload.status,
                    "old_error_code": old_error_code,
                    "old_error_message": old_error_message,
                    "error_code": payload.error_code,
                    "error_message": payload.error_message,
                    "delivery_time": new_delivery_time.isoformat() if new_delivery_time else None,
                },
                auto_commit=False,
            )
        except Exception:
            pass

        await session.commit()

        return ShippingStatusUpdateOut(
            ok=True, id=record_id, status=payload.status, delivery_time=new_delivery_time
        )
