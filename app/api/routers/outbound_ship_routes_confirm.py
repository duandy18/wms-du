# app/api/routers/outbound_ship_routes_confirm.py
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.routers.outbound_ship_schemas import ShipConfirmRequest, ShipConfirmResponse
from app.services.ship_service import ShipService


def register(router: APIRouter) -> None:
    @router.post("/ship/confirm", response_model=ShipConfirmResponse)
    async def confirm_ship(
        payload: ShipConfirmRequest,
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> ShipConfirmResponse:
        """
        记录一次发货完成事件（Phase 2）

        - 不做库存扣减（库存扣减已由 Outbound/Pick 链路完成）
        - 写审计事件（OUTBOUND / SHIP_COMMIT），供 Trace / Lifecycle 使用
        - 写 shipping_records（发货账本），用于后续对账 / KPI / 成本分析
        """
        svc = ShipService(session)

        # 审计事件 meta：带上尽可能多的结构化字段
        meta: Dict[str, Any] = {}
        if payload.meta:
            meta.update(payload.meta)

        if payload.carrier:
            meta["carrier"] = payload.carrier
        if payload.carrier_name:
            meta["carrier_name"] = payload.carrier_name
        if payload.tracking_no:
            meta["tracking_no"] = payload.tracking_no

        if payload.gross_weight_kg is not None:
            meta["gross_weight_kg"] = payload.gross_weight_kg
        if payload.packaging_weight_kg is not None:
            meta["packaging_weight_kg"] = payload.packaging_weight_kg

        if payload.cost_estimated is not None:
            meta["cost_estimated"] = payload.cost_estimated
        if payload.cost_real is not None:
            meta["cost_real"] = payload.cost_real

        if payload.status:
            meta["status"] = payload.status
        if payload.error_code:
            meta["error_code"] = payload.error_code
        if payload.error_message:
            meta["error_message"] = payload.error_message
        if payload.delivery_time:
            meta["delivery_time"] = payload.delivery_time.isoformat()

        if payload.warehouse_id is not None:
            meta["warehouse_id"] = payload.warehouse_id

        # Step 1: 写审计事件
        data = await svc.commit(
            ref=payload.ref,
            platform=payload.platform,
            shop_id=payload.shop_id,
            trace_id=payload.trace_id,
            meta=meta or None,
        )

        # 把 meta 转成 JSON 字符串，避免 asyncpg jsonb encoder 报错
        json_meta: Optional[str]
        if meta:
            json_meta = json.dumps(meta, ensure_ascii=False)
        else:
            json_meta = None

        # Step 2: 写 shipping_records
        insert_sql = text(
            """
            INSERT INTO shipping_records (
                order_ref,
                platform,
                shop_id,
                carrier_code,
                carrier_name,
                tracking_no,
                trace_id,
                warehouse_id,
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
                :carrier_code,
                :carrier_name,
                :tracking_no,
                :trace_id,
                :warehouse_id,
                :weight_kg,
                :gross_weight_kg,
                :packaging_weight_kg,
                :cost_estimated,
                :cost_real,
                :delivery_time,
                :status,
                :error_code,
                :error_message,
                :meta
            )
            """
        )

        await session.execute(
            insert_sql,
            {
                "order_ref": payload.ref,
                "platform": payload.platform.upper(),
                "shop_id": payload.shop_id,
                "carrier_code": payload.carrier,
                "carrier_name": payload.carrier_name,
                "tracking_no": payload.tracking_no,
                "trace_id": payload.trace_id,
                "warehouse_id": payload.warehouse_id,
                "weight_kg": None,  # 未来可以存“净重估算”
                "gross_weight_kg": payload.gross_weight_kg,
                "packaging_weight_kg": payload.packaging_weight_kg,
                "cost_estimated": payload.cost_estimated,
                "cost_real": payload.cost_real,
                "delivery_time": payload.delivery_time,
                "status": payload.status or "IN_TRANSIT",
                "error_code": payload.error_code,
                "error_message": payload.error_message,
                "meta": json_meta,
            },
        )

        await session.commit()

        return ShipConfirmResponse(
            ok=data.get("ok", True),
            ref=payload.ref,
            trace_id=payload.trace_id,
        )
