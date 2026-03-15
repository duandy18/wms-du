# app/tms/shipment/repository.py
# 分拆说明：
# - 本文件从 service.py 中拆出 Shipment / ShippingRecord 持久化 SQL；
# - 目标是统一收口 transport_shipments 与 shipping_records 的读写，
#   避免应用编排层直接夹杂大量 SQL text。
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .contracts import ShipmentApplicationError


def _json_dumps(meta: dict[str, object]) -> str:
    return json.dumps(meta, ensure_ascii=False)


def _raise(*, status_code: int, code: str, message: str) -> None:
    raise ShipmentApplicationError(
        status_code=status_code,
        code=code,
        message=message,
    )


async def upsert_transport_shipment_for_waybill(
    session: AsyncSession,
    *,
    order_ref: str,
    platform: str,
    shop_id: str,
    trace_id: str | None,
    warehouse_id: int,
    shipping_provider_id: int,
    quote_snapshot: dict[str, object],
    weight_kg: float,
    receiver_name: str | None,
    receiver_phone: str | None,
    province: str | None,
    city: str | None,
    district: str | None,
    address_detail: str | None,
    tracking_no: str,
    carrier_code: str | None,
    carrier_name: str | None,
    status: str,
    delivery_time: datetime | None,
    error_code: str | None,
    error_message: str | None,
) -> int:
    row = await session.execute(
        text(
            """
            INSERT INTO transport_shipments (
                order_ref,
                platform,
                shop_id,
                trace_id,
                warehouse_id,
                shipping_provider_id,
                quote_snapshot,
                weight_kg,
                receiver_name,
                receiver_phone,
                province,
                city,
                district,
                address_detail,
                tracking_no,
                carrier_code,
                carrier_name,
                status,
                delivery_time,
                error_code,
                error_message
            )
            VALUES (
                :order_ref,
                :platform,
                :shop_id,
                :trace_id,
                :warehouse_id,
                :shipping_provider_id,
                CAST(:quote_snapshot AS jsonb),
                :weight_kg,
                :receiver_name,
                :receiver_phone,
                :province,
                :city,
                :district,
                :address_detail,
                :tracking_no,
                :carrier_code,
                :carrier_name,
                :status,
                :delivery_time,
                :error_code,
                :error_message
            )
            ON CONFLICT (platform, shop_id, order_ref) DO UPDATE SET
                trace_id = EXCLUDED.trace_id,
                warehouse_id = EXCLUDED.warehouse_id,
                shipping_provider_id = EXCLUDED.shipping_provider_id,
                quote_snapshot = EXCLUDED.quote_snapshot,
                weight_kg = EXCLUDED.weight_kg,
                receiver_name = EXCLUDED.receiver_name,
                receiver_phone = EXCLUDED.receiver_phone,
                province = EXCLUDED.province,
                city = EXCLUDED.city,
                district = EXCLUDED.district,
                address_detail = EXCLUDED.address_detail,
                tracking_no = EXCLUDED.tracking_no,
                carrier_code = EXCLUDED.carrier_code,
                carrier_name = EXCLUDED.carrier_name,
                status = EXCLUDED.status,
                delivery_time = EXCLUDED.delivery_time,
                error_code = EXCLUDED.error_code,
                error_message = EXCLUDED.error_message,
                updated_at = now()
            RETURNING id
            """
        ),
        {
            "order_ref": order_ref,
            "platform": platform.upper(),
            "shop_id": shop_id,
            "trace_id": trace_id,
            "warehouse_id": warehouse_id,
            "shipping_provider_id": shipping_provider_id,
            "quote_snapshot": _json_dumps(quote_snapshot),
            "weight_kg": weight_kg,
            "receiver_name": receiver_name,
            "receiver_phone": receiver_phone,
            "province": province,
            "city": city,
            "district": district,
            "address_detail": address_detail,
            "tracking_no": tracking_no,
            "carrier_code": carrier_code,
            "carrier_name": carrier_name,
            "status": status,
            "delivery_time": delivery_time,
            "error_code": error_code,
            "error_message": error_message,
        },
    )
    shipment_id = row.scalar_one_or_none()
    if shipment_id is None:
        _raise(
            status_code=500,
            code="SHIP_WITH_WAYBILL_SHIPMENT_UPSERT_FAILED",
            message="failed to persist transport_shipment",
        )
    return int(shipment_id)


async def upsert_waybill_shipping_record(
    session: AsyncSession,
    *,
    shipment_id: int,
    order_ref: str,
    platform: str,
    shop_id: str,
    warehouse_id: int,
    shipping_provider_id: int,
    carrier_code: str | None,
    carrier_name: str | None,
    tracking_no: str,
    trace_id: str | None,
    gross_weight_kg: float,
    cost_estimated: float,
    meta: dict[str, object],
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO shipping_records (
                order_ref,
                platform,
                shop_id,
                shipment_id,
                warehouse_id,
                shipping_provider_id,
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
                reconcile_status,
                error_code,
                error_message,
                meta
            )
            VALUES (
                :order_ref,
                :platform,
                :shop_id,
                :shipment_id,
                :warehouse_id,
                :shipping_provider_id,
                :carrier_code,
                :carrier_name,
                :tracking_no,
                :trace_id,
                :weight_kg,
                :gross_weight_kg,
                :packaging_weight_kg,
                :cost_estimated,
                :cost_real,
                :delivery_time,
                :status,
                :reconcile_status,
                :error_code,
                :error_message,
                CAST(:meta AS jsonb)
            )
            ON CONFLICT (platform, shop_id, order_ref) DO UPDATE SET
                shipment_id = EXCLUDED.shipment_id,
                warehouse_id = EXCLUDED.warehouse_id,
                shipping_provider_id = EXCLUDED.shipping_provider_id,
                carrier_code = EXCLUDED.carrier_code,
                carrier_name = EXCLUDED.carrier_name,
                tracking_no = EXCLUDED.tracking_no,
                trace_id = EXCLUDED.trace_id,
                weight_kg = EXCLUDED.weight_kg,
                gross_weight_kg = EXCLUDED.gross_weight_kg,
                packaging_weight_kg = EXCLUDED.packaging_weight_kg,
                cost_estimated = EXCLUDED.cost_estimated,
                cost_real = EXCLUDED.cost_real,
                delivery_time = EXCLUDED.delivery_time,
                status = EXCLUDED.status,
                reconcile_status = EXCLUDED.reconcile_status,
                error_code = EXCLUDED.error_code,
                error_message = EXCLUDED.error_message,
                meta = EXCLUDED.meta
            """
        ),
        {
            "order_ref": order_ref,
            "platform": platform.upper(),
            "shop_id": shop_id,
            "shipment_id": shipment_id,
            "warehouse_id": warehouse_id,
            "shipping_provider_id": shipping_provider_id,
            "carrier_code": carrier_code,
            "carrier_name": carrier_name,
            "tracking_no": tracking_no,
            "trace_id": trace_id,
            "weight_kg": None,
            "gross_weight_kg": gross_weight_kg,
            "packaging_weight_kg": None,
            "cost_estimated": cost_estimated,
            "cost_real": None,
            "delivery_time": None,
            "status": "IN_TRANSIT",
            "reconcile_status": "UNMATCHED",
            "error_code": None,
            "error_message": None,
            "meta": _json_dumps(meta),
        },
    )


async def get_shipping_record_for_status_update(
    session: AsyncSession,
    record_id: int,
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  id,
                  shipment_id,
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
            ),
            {"id": record_id},
        )
    ).mappings().first()

    return dict(row) if row is not None else None


async def update_shipping_record_status(
    session: AsyncSession,
    *,
    record_id: int,
    status: str,
    delivery_time: datetime | None,
    error_code: str | None,
    error_message: str | None,
    meta: dict[str, object],
) -> None:
    await session.execute(
        text(
            """
            UPDATE shipping_records
               SET status = :status,
                   delivery_time = :delivery_time,
                   error_code = :error_code,
                   error_message = :error_message,
                   meta = CAST(:meta AS jsonb)
             WHERE id = :id
            """
        ),
        {
            "id": record_id,
            "status": status,
            "delivery_time": delivery_time,
            "error_code": error_code,
            "error_message": error_message,
            "meta": _json_dumps(meta),
        },
    )


async def get_transport_shipment_id_by_record_id(
    session: AsyncSession,
    *,
    record_id: int,
) -> int | None:
    row = (
        await session.execute(
            text(
                """
                SELECT shipment_id
                FROM shipping_records
                WHERE id = :id
                LIMIT 1
                """
            ),
            {"id": record_id},
        )
    ).first()

    if row is None:
        return None

    shipment_id = row[0]
    return int(shipment_id) if shipment_id is not None else None


async def update_transport_shipment_status(
    session: AsyncSession,
    *,
    shipment_id: int,
    status: str,
    delivery_time: datetime | None,
    error_code: str | None,
    error_message: str | None,
) -> None:
    await session.execute(
        text(
            """
            UPDATE transport_shipments
               SET status = :status,
                   delivery_time = :delivery_time,
                   error_code = :error_code,
                   error_message = :error_message,
                   updated_at = now()
             WHERE id = :id
            """
        ),
        {
            "id": shipment_id,
            "status": status,
            "delivery_time": delivery_time,
            "error_code": error_code,
            "error_message": error_message,
        },
    )
