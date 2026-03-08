# app/api/routers/outbound_ship_routes_confirm.py
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.routers.outbound_ship_schemas import ShipConfirmRequest, ShipConfirmResponse
from app.services.audit_writer import AuditEventWriter
from app.services.ship_service import ShipService


class ShipConfirmErrorCode:
    WAREHOUSE_REQUIRED = "SHIP_CONFIRM_WAREHOUSE_REQUIRED"
    CARRIER_REQUIRED = "SHIP_CONFIRM_CARRIER_REQUIRED"
    SCHEME_REQUIRED = "SHIP_CONFIRM_SCHEME_REQUIRED"

    ORDER_DUP = "SHIP_CONFIRM_ORDER_DUP"
    CARRIER_NOT_AVAILABLE = "SHIP_CONFIRM_CARRIER_NOT_AVAILABLE"
    CARRIER_NOT_ENABLED_FOR_WAREHOUSE = "SHIP_CONFIRM_CARRIER_NOT_ENABLED_FOR_WAREHOUSE"
    SCHEME_NOT_AVAILABLE_FOR_WAREHOUSE = "SHIP_CONFIRM_SCHEME_NOT_AVAILABLE_FOR_WAREHOUSE"
    SCHEME_NOT_BELONG_TO_CARRIER = "SHIP_CONFIRM_SCHEME_NOT_BELONG_TO_CARRIER"
    TRACKING_DUP = "SHIP_CONFIRM_TRACKING_DUP"


def _raise_422(code: str, message: str) -> None:
    raise HTTPException(status_code=422, detail={"code": code, "message": message})


def _raise_409(code: str, message: str) -> None:
    raise HTTPException(status_code=409, detail={"code": code, "message": message})


def register(router: APIRouter) -> None:

    @router.post("/ship/confirm", response_model=ShipConfirmResponse)
    async def confirm_ship(
        payload: ShipConfirmRequest,
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> ShipConfirmResponse:

        svc = ShipService(session)
        platform_norm = payload.platform.upper()

        async def _audit_reject(error_code: str, message: str) -> None:
            meta: Dict[str, Any] = {
                "platform": platform_norm,
                "shop_id": payload.shop_id,
                "error_code": error_code,
                "message": message,
            }

            if payload.trace_id:
                meta["trace_id"] = payload.trace_id

            if payload.warehouse_id is not None:
                meta["warehouse_id"] = payload.warehouse_id

            meta["provider_id"] = int(payload.shipping_provider_id)

            if getattr(payload, "scheme_id", None) is not None:
                meta["scheme_id"] = int(getattr(payload, "scheme_id"))

            await AuditEventWriter.write(
                session,
                flow="OUTBOUND",
                event="SHIP_CONFIRM_REJECT",
                ref=payload.ref,
                trace_id=payload.trace_id,
                meta=meta,
                auto_commit=True,
            )

        try:

            if payload.warehouse_id is None:
                _raise_422(ShipConfirmErrorCode.WAREHOUSE_REQUIRED, "warehouse_id is required")

            if int(payload.shipping_provider_id) <= 0:
                _raise_422(ShipConfirmErrorCode.CARRIER_REQUIRED, "shipping_provider_id is required")

            if getattr(payload, "scheme_id", None) is None:
                _raise_422(ShipConfirmErrorCode.SCHEME_REQUIRED, "scheme_id is required")

            wid = int(payload.warehouse_id)
            provider_id = int(payload.shipping_provider_id)
            sid = int(getattr(payload, "scheme_id"))

            # provider check
            prow = (
                await session.execute(
                    text(
                        """
                        SELECT id, code, name, active
                        FROM shipping_providers
                        WHERE id = :pid
                        LIMIT 1
                        """
                    ),
                    {"pid": provider_id},
                )
            ).mappings().first()

            if not prow or not bool(prow.get("active", True)):
                _raise_409(ShipConfirmErrorCode.CARRIER_NOT_AVAILABLE, "carrier not available")

            provider_name = str(prow.get("name") or "")
            provider_code = str(prow.get("code") or "")

            # warehouse binding
            wsp = (
                await session.execute(
                    text(
                        """
                        SELECT 1
                        FROM warehouse_shipping_providers
                        WHERE warehouse_id = :wid
                          AND shipping_provider_id = :pid
                          AND active = true
                        LIMIT 1
                        """
                    ),
                    {"wid": wid, "pid": provider_id},
                )
            ).first()

            if not wsp:
                _raise_409(
                    ShipConfirmErrorCode.CARRIER_NOT_ENABLED_FOR_WAREHOUSE,
                    "carrier not enabled for this warehouse",
                )

            # scheme check（终态合同）
            sch_row = (
                await session.execute(
                    text(
                        """
                        SELECT
                          sch.id,
                          sch.shipping_provider_id
                        FROM shipping_provider_pricing_schemes sch
                        WHERE sch.id = :sid
                          AND sch.warehouse_id = :wid
                          AND sch.status = 'active'
                          AND sch.archived_at IS NULL
                          AND (sch.effective_from IS NULL OR sch.effective_from <= now())
                          AND (sch.effective_to IS NULL OR sch.effective_to >= now())
                        LIMIT 1
                        """
                    ),
                    {"sid": sid, "wid": wid},
                )
            ).mappings().first()

            if not sch_row:
                _raise_409(
                    ShipConfirmErrorCode.SCHEME_NOT_AVAILABLE_FOR_WAREHOUSE,
                    "scheme not available for this warehouse",
                )

            if int(sch_row["shipping_provider_id"]) != provider_id:
                _raise_409(
                    ShipConfirmErrorCode.SCHEME_NOT_BELONG_TO_CARRIER,
                    "scheme does not belong to selected carrier",
                )

            # tracking dedupe
            tno: Optional[str] = None

            if payload.tracking_no and payload.tracking_no.strip():
                tno = payload.tracking_no.strip()

                dup_tno = (
                    await session.execute(
                        text(
                            """
                            SELECT 1
                            FROM shipping_records
                            WHERE shipping_provider_id = :pid
                              AND tracking_no = :tracking_no
                            LIMIT 1
                            """
                        ),
                        {"pid": provider_id, "tracking_no": tno},
                    )
                ).first()

                if dup_tno:
                    _raise_409(
                        ShipConfirmErrorCode.TRACKING_DUP,
                        "tracking_no already exists for this provider",
                    )

            meta: Dict[str, Any] = payload.meta or {}

            meta.update(
                {
                    "provider_id": provider_id,
                    "carrier_code": provider_code,
                    "carrier_name": provider_name,
                    "scheme_id": sid,
                    "warehouse_id": wid,
                }
            )

            data = await svc.commit(
                ref=payload.ref,
                platform=payload.platform,
                shop_id=payload.shop_id,
                trace_id=payload.trace_id,
                meta=meta or None,
            )

            json_meta = json.dumps(meta, ensure_ascii=False) if meta else None

            insert_sql = text(
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
                    trace_id,
                    meta
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
                    :trace_id,
                    :meta
                )
                ON CONFLICT (platform, shop_id, order_ref) DO NOTHING
                RETURNING id
                """
            )

            inserted = (
                await session.execute(
                    insert_sql,
                    {
                        "order_ref": payload.ref,
                        "platform": platform_norm,
                        "shop_id": payload.shop_id,
                        "warehouse_id": wid,
                        "shipping_provider_id": provider_id,
                        "carrier_code": provider_code,
                        "carrier_name": provider_name,
                        "tracking_no": tno,
                        "trace_id": payload.trace_id,
                        "meta": json_meta,
                    },
                )
            ).scalar_one_or_none()

            if inserted is None:
                await session.rollback()
                _raise_409(ShipConfirmErrorCode.ORDER_DUP, "order already confirmed")

            await session.commit()

            return ShipConfirmResponse(ok=data.get("ok", True), ref=payload.ref, trace_id=payload.trace_id)

        except HTTPException as e:
            if e.status_code in (422, 409) and isinstance(e.detail, dict):
                code = e.detail.get("code")
                msg = e.detail.get("message")

                if isinstance(code, str) and isinstance(msg, str):
                    await _audit_reject(code, msg)

            raise
