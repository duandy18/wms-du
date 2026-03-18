# app/tms/shipment/repository.py
# 分拆说明：
# - 本文件从 service.py 中拆出 ShippingRecord 持久化 SQL；
# - 当前阶段 shipping_records 已收口为“物流台帐表”；
# - 不再承担物流状态，不再承担对账结果，不再依赖 transport_shipments。
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def upsert_waybill_shipping_record(
    session: AsyncSession,
    *,
    order_ref: str,
    platform: str,
    shop_id: str,
    warehouse_id: int,
    shipping_provider_id: int,
    carrier_code: str | None,
    carrier_name: str | None,
    tracking_no: str,
    gross_weight_kg: float,
    freight_estimated: float | None,
    surcharge_estimated: float | None,
    cost_estimated: float,
    length_cm: float | None,
    width_cm: float | None,
    height_cm: float | None,
    sender: str | None,
    dest_province: str | None,
    dest_city: str | None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO shipping_records (
                order_ref,
                platform,
                shop_id,
                warehouse_id,
                shipping_provider_id,
                carrier_code,
                carrier_name,
                tracking_no,
                gross_weight_kg,
                freight_estimated,
                surcharge_estimated,
                cost_estimated,
                length_cm,
                width_cm,
                height_cm,
                sender,
                dest_province,
                dest_city
            )
            VALUES (
                :order_ref,
                :platform,
                :shop_id,
                :warehouse_id,
                :shipping_provider_id,
                :carrier_code,
                :carrier_name,
                :tracking_no,
                :gross_weight_kg,
                :freight_estimated,
                :surcharge_estimated,
                :cost_estimated,
                :length_cm,
                :width_cm,
                :height_cm,
                :sender,
                :dest_province,
                :dest_city
            )
            ON CONFLICT (platform, shop_id, order_ref) DO UPDATE SET
                warehouse_id = EXCLUDED.warehouse_id,
                shipping_provider_id = EXCLUDED.shipping_provider_id,
                carrier_code = EXCLUDED.carrier_code,
                carrier_name = EXCLUDED.carrier_name,
                tracking_no = EXCLUDED.tracking_no,
                gross_weight_kg = EXCLUDED.gross_weight_kg,
                freight_estimated = EXCLUDED.freight_estimated,
                surcharge_estimated = EXCLUDED.surcharge_estimated,
                cost_estimated = EXCLUDED.cost_estimated,
                length_cm = EXCLUDED.length_cm,
                width_cm = EXCLUDED.width_cm,
                height_cm = EXCLUDED.height_cm,
                sender = EXCLUDED.sender,
                dest_province = EXCLUDED.dest_province,
                dest_city = EXCLUDED.dest_city
            """
        ),
        {
            "order_ref": order_ref,
            "platform": platform.upper(),
            "shop_id": shop_id,
            "warehouse_id": warehouse_id,
            "shipping_provider_id": shipping_provider_id,
            "carrier_code": carrier_code,
            "carrier_name": carrier_name,
            "tracking_no": tracking_no,
            "gross_weight_kg": gross_weight_kg,
            "freight_estimated": freight_estimated,
            "surcharge_estimated": surcharge_estimated,
            "cost_estimated": cost_estimated,
            "length_cm": length_cm,
            "width_cm": width_cm,
            "height_cm": height_cm,
            "sender": sender,
            "dest_province": dest_province,
            "dest_city": dest_city,
        },
    )
