# app/tms/shipment/status_sync.py
# 分拆说明：
# - 本文件从 service.py / job 侧提取 Shipment 状态同步规则；
# - 目标是统一收口 shipping_records(projection) 与 transport_shipments(主实体) 的状态双写；
# - Shipment 状态值与状态转移约束已下沉到 state_machine.py；
# - 当前阶段不承载审计写入与事务提交。
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from .contracts import ShipmentApplicationError
from .repository import (
    get_shipping_record_for_status_update,
    update_shipping_record_status,
    update_transport_shipment_status,
)
from .state_machine import (
    ensure_shipment_status_transition,
    ensure_shipment_status_value,
)


@dataclass(frozen=True, slots=True)
class AppliedShipmentStatusUpdate:
    record_id: int
    shipment_id: int
    order_ref: str
    trace_id: str | None
    old_status: str | None
    old_error_code: str | None
    old_error_message: str | None
    status: str
    delivery_time: datetime | None


def _raise(*, status_code: int, code: str, message: str) -> None:
    raise ShipmentApplicationError(
        status_code=status_code,
        code=code,
        message=message,
    )


async def apply_shipment_status_update(
    session: AsyncSession,
    *,
    record_id: int,
    status: str,
    delivery_time: datetime | None,
    error_code: str | None,
    error_message: str | None,
    meta: dict[str, object] | None,
) -> AppliedShipmentStatusUpdate:
    row = await get_shipping_record_for_status_update(session, record_id)

    if row is None:
        _raise(
            status_code=404,
            code="SHIPPING_RECORD_NOT_FOUND",
            message="shipping_record not found",
        )

    shipment_id_raw = row.get("shipment_id")
    if shipment_id_raw is None:
        _raise(
            status_code=409,
            code="SHIPPING_RECORD_SHIPMENT_ID_REQUIRED",
            message="shipping_record.shipment_id is required",
        )

    shipment_id = int(shipment_id_raw)
    order_ref = str(row["order_ref"])
    trace_id = cast(str | None, row.get("trace_id"))
    old_status = cast(str | None, row.get("status"))
    old_delivery_time = cast(datetime | None, row.get("delivery_time"))
    old_meta_raw = row.get("meta")
    old_meta = dict(old_meta_raw) if isinstance(old_meta_raw, dict) else {}
    old_error_code = cast(str | None, row.get("error_code"))
    old_error_message = cast(str | None, row.get("error_message"))

    normalized_status = ensure_shipment_status_value(status)
    ensure_shipment_status_transition(
        old_status=old_status,
        new_status=normalized_status,
    )

    if delivery_time is not None:
        new_delivery_time = delivery_time
    elif normalized_status == "DELIVERED" and old_delivery_time is None:
        new_delivery_time = datetime.now(timezone.utc)
    else:
        new_delivery_time = old_delivery_time

    new_meta: dict[str, object] = dict(old_meta)
    if meta:
        new_meta.update(meta)
    if error_code is not None:
        new_meta["error_code"] = error_code
    if error_message is not None:
        new_meta["error_message"] = error_message

    await update_shipping_record_status(
        session,
        record_id=record_id,
        status=normalized_status,
        delivery_time=new_delivery_time,
        error_code=error_code,
        error_message=error_message,
        meta=new_meta,
    )

    await update_transport_shipment_status(
        session,
        shipment_id=shipment_id,
        status=normalized_status,
        delivery_time=new_delivery_time,
        error_code=error_code,
        error_message=error_message,
    )

    return AppliedShipmentStatusUpdate(
        record_id=record_id,
        shipment_id=shipment_id,
        order_ref=order_ref,
        trace_id=trace_id,
        old_status=old_status,
        old_error_code=old_error_code,
        old_error_message=old_error_message,
        status=normalized_status,
        delivery_time=new_delivery_time,
    )
