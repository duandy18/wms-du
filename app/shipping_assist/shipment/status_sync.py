# app/shipping_assist/shipment/status_sync.py
# 分拆说明：
# - 该模块原用于 shipping_records / transport_shipments 状态双写；
# - 当前路线已放弃“本地维护物流状态真相”；
# - 物流状态改为平台侧读取，因此本模块废止；
# - 保留同名函数，仅用于给旧调用方返回明确错误。
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from .contracts import ShipmentApplicationError


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
    del session
    del record_id
    del status
    del delivery_time
    del error_code
    del error_message
    del meta

    _raise(
        status_code=410,
        code="SHIPMENT_STATUS_SYNC_REMOVED",
        message="shipment status sync has been removed; logistics status should be read from platform APIs",
    )
