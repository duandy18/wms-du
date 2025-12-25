# app/api/routers/orders_fulfillment_v2_routes_4_ship_with_waybill.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.orders_fulfillment_v2_helpers import (
    extract_cost_estimated,
    extract_quote_snapshot,
    get_order_ref_and_trace_id,
    validate_quote_snapshot,
)
from app.api.routers.orders_fulfillment_v2_schemas import (
    ShipWithWaybillRequest,
    ShipWithWaybillResponse,
)
from app.services.ship_service import ShipService
from app.services.waybill_service import WaybillRequest, WaybillService


def register(router: APIRouter) -> None:
    @router.post(
        "/{platform}/{shop_id}/{ext_order_no}/ship-with-waybill",
        response_model=ShipWithWaybillResponse,
    )
    async def order_ship_with_waybill(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        body: ShipWithWaybillRequest,
        session: AsyncSession = Depends(get_session),
    ):
        plat = platform.upper()

        order_ref, trace_id = await get_order_ref_and_trace_id(
            session=session,
            platform=plat,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
        )

        quote_snapshot = extract_quote_snapshot(body.meta)
        if not quote_snapshot:
            raise HTTPException(status_code=422, detail="meta.quote_snapshot is required")
        validate_quote_snapshot(quote_snapshot)
        cost_estimated = extract_cost_estimated(quote_snapshot)

        waybill_svc = WaybillService()
        wb_req = WaybillRequest(
            provider_code=body.carrier_code,
            platform=plat,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            receiver={
                "name": body.receiver_name,
                "phone": body.receiver_phone,
                "province": body.province,
                "city": body.city,
                "district": body.district,
                "detail": body.address_detail,
            },
            cargo={"weight_kg": float(body.weight_kg or 0.0)},
            extras={},
        )
        wb_result = await waybill_svc.request_waybill(wb_req)
        if not wb_result.ok or not wb_result.tracking_no:
            raise HTTPException(
                status_code=502,
                detail=f"waybill request failed: {wb_result.error_code or ''} {wb_result.error_message or ''}",
            )

        tracking_no = wb_result.tracking_no
        occurred_at = datetime.now(timezone.utc)

        meta: Dict[str, Any] = {
            "platform": plat,
            "shop_id": shop_id,
            "warehouse_id": int(body.warehouse_id),
            "occurred_at": occurred_at.isoformat(),
            "tracking_no": tracking_no,
            "carrier_code": body.carrier_code,
            "carrier_name": body.carrier_name,
            "gross_weight_kg": float(body.weight_kg or 0.0),
            "receiver": {
                "name": body.receiver_name,
                "phone": body.receiver_phone,
                "province": body.province,
                "city": body.city,
                "district": body.district,
                "detail": body.address_detail,
            },
            "waybill_source": "PLATFORM_FAKE",
            "cost_estimated": cost_estimated,
            "quote_snapshot": quote_snapshot,  # ✅ 整包固化
        }

        svc = ShipService(session=session)
        try:
            audit_res = await svc.commit(
                ref=order_ref, platform=plat, shop_id=shop_id, trace_id=trace_id, meta=meta
            )
        except Exception:
            await session.rollback()
            raise

        insert_sql = text(
            """
            INSERT INTO shipping_records (
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
                meta
            )
            VALUES (
                :order_ref,
                :platform,
                :shop_id,
                :warehouse_id,
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
                :error_code,
                :error_message,
                CAST(:meta AS jsonb)
            )
            """
        )

        json_meta = json.dumps(meta, ensure_ascii=False)

        await session.execute(
            insert_sql,
            {
                "order_ref": order_ref,
                "platform": plat,
                "shop_id": shop_id,
                "warehouse_id": int(body.warehouse_id),
                "carrier_code": body.carrier_code,
                "carrier_name": body.carrier_name,
                "tracking_no": tracking_no,
                "trace_id": trace_id,
                "weight_kg": None,
                "gross_weight_kg": float(body.weight_kg or 0.0),
                "packaging_weight_kg": None,
                "cost_estimated": cost_estimated,
                "cost_real": None,
                "delivery_time": None,
                "status": "IN_TRANSIT",
                "error_code": None,
                "error_message": None,
                "meta": json_meta,
            },
        )

        await session.commit()

        return ShipWithWaybillResponse(
            ok=audit_res.get("ok", True),
            ref=order_ref,
            tracking_no=tracking_no,
            carrier_code=body.carrier_code,
            carrier_name=body.carrier_name,
            status="IN_TRANSIT",
            label_base64=None,
            label_format=None,
        )
