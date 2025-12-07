# app/api/routers/shipping_records.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.services.audit_writer import AuditEventWriter

router = APIRouter(tags=["shipping-records"])


class ShippingRecordOut(BaseModel):
    id: int
    order_ref: str
    platform: str
    shop_id: str
    warehouse_id: Optional[int] = Field(None)

    carrier_code: Optional[str] = None
    carrier_name: Optional[str] = None
    tracking_no: Optional[str] = None

    trace_id: Optional[str] = None

    weight_kg: Optional[float] = None
    gross_weight_kg: Optional[float] = None
    packaging_weight_kg: Optional[float] = None

    cost_estimated: Optional[float] = None
    cost_real: Optional[float] = None

    delivery_time: Optional[datetime] = None
    status: Optional[str] = None

    error_code: Optional[str] = None
    error_message: Optional[str] = None

    meta: Optional[dict] = None
    created_at: datetime


class ShippingStatusUpdateIn(BaseModel):
    status: Literal["IN_TRANSIT", "DELIVERED", "LOST", "RETURNED"] = Field(
        ...,
        description="发货状态：IN_TRANSIT / DELIVERED / LOST / RETURNED",
    )
    delivery_time: Optional[datetime] = Field(
        None,
        description="状态为 DELIVERED 时，如未提供则默认使用当前时间",
    )
    error_code: Optional[str] = Field(None, description="错误码（LOST/RETURNED 时可选）")
    error_message: Optional[str] = Field(None, description="错误说明（LOST/RETURNED 时可选）")
    meta: Optional[dict] = Field(
        None,
        description="附加 meta，将 merge 进原 meta（不会丢弃原有字段）",
    )


class ShippingStatusUpdateOut(BaseModel):
    ok: bool = True
    id: int
    status: str
    delivery_time: Optional[datetime] = None


# -------- /shipping-records/{id} --------


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


# -------- /shipping-records/by-ref/{order_ref} --------


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
    """
    按 order_ref 查询 shipping_records。

    - 一个订单通常只有一条发货记录；
    - 但允许多次发货 → 返回多条，按 created_at DESC 排序。
    """
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


# -------- /shipping-records/{id}/status --------


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
    """
    用于在发货后更新 shipping_records 的状态：

    - 正向流转：IN_TRANSIT → DELIVERED
    - 异常流转：IN_TRANSIT → LOST / RETURNED

    同时：
    - DELIVERED：如未提供 delivery_time，则默认使用当前时间；
    - error_code / error_message 写入表字段，并 merge 到 meta 中；
    - 写一条 OUTBOUND / SHIP_STATUS_UPDATE 审计事件，方便诊断 / Lifecycle 使用。
    """
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

    # 2) 计算新的 delivery_time
    if payload.delivery_time is not None:
        new_delivery_time = payload.delivery_time
    elif payload.status == "DELIVERED" and old_delivery_time is None:
        new_delivery_time = datetime.now(timezone.utc)
    else:
        new_delivery_time = old_delivery_time

    # 3) 合并 meta & 错误信息
    new_meta = dict(old_meta)
    if payload.meta:
        new_meta.update(payload.meta)
    if payload.error_code is not None:
        new_meta["error_code"] = payload.error_code
    if payload.error_message is not None:
        new_meta["error_message"] = payload.error_message

    # 按你项目的 asyncpg JSONB 配置，需要传字符串而不是 dict
    if new_meta:
        json_meta: Optional[str] = json.dumps(new_meta, ensure_ascii=False)
    else:
        json_meta = None

    # 4) 更新 shipping_records
    update_sql = text(
        """
        UPDATE shipping_records
           SET status = :status,
               delivery_time = :delivery_time,
               error_code = :error_code,
               error_message = :error_message,
               meta = :meta
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

    # 5) 写审计事件（OUTBOUND / SHIP_STATUS_UPDATE）
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
        # 审计失败不能影响主流程，留给日志/监控观察。
        pass

    await session.commit()

    return ShippingStatusUpdateOut(
        ok=True,
        id=record_id,
        status=payload.status,
        delivery_time=new_delivery_time,
    )
