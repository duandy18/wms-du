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
    # 422 - missing/invalid fields
    WAREHOUSE_REQUIRED = "SHIP_CONFIRM_WAREHOUSE_REQUIRED"
    CARRIER_REQUIRED = "SHIP_CONFIRM_CARRIER_REQUIRED"  # 复用错误码：现在指 provider_id 缺失
    SCHEME_REQUIRED = "SHIP_CONFIRM_SCHEME_REQUIRED"

    # 409 - contract conflicts
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
        """
        记录一次发货完成事件（Phase 3 + 幂等守门 + 可统计错误码）

        合同（刚性）：
        - ref 在 (platform, shop_id) 维度必须幂等（防重复确认）
        - warehouse_id 必填
        - shipping_provider_id 必填且必须是该仓可服务（warehouse_shipping_providers.active=true）
        - scheme_id 必填且必须绑定该仓、有效期命中、且属于该 provider
        - tracking_no 若提供：(carrier_code, tracking_no) 唯一（carrier_code 来自 provider.code）

        错误返回：
        - 422：缺字段/入参不合法（detail: {code,message}）
        - 409：合同冲突（detail: {code,message}）

        失败审计（Phase 4 样板）：
        - 对所有 422/409，写 audit_events：flow=OUTBOUND, event=SHIP_CONFIRM_REJECT
          meta 包含 error_code / message / platform / shop_id / ref / trace_id / warehouse_id / provider_id / scheme_id
        """
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
            # Phase 3：硬校验（合同守门）
            if payload.warehouse_id is None:
                _raise_422(ShipConfirmErrorCode.WAREHOUSE_REQUIRED, "warehouse_id is required")
            if int(payload.shipping_provider_id) <= 0:
                _raise_422(ShipConfirmErrorCode.CARRIER_REQUIRED, "shipping_provider_id is required")
            if getattr(payload, "scheme_id", None) is None:
                _raise_422(ShipConfirmErrorCode.SCHEME_REQUIRED, "scheme_id is required")

            wid = int(payload.warehouse_id)
            provider_id = int(payload.shipping_provider_id)
            sid = int(getattr(payload, "scheme_id"))

            # 1) provider_id -> provider（active）
            prow = (
                await session.execute(
                    text("SELECT id, code, name, active FROM shipping_providers WHERE id = :pid LIMIT 1"),
                    {"pid": provider_id},
                )
            ).mappings().first()
            if not prow or not bool(prow.get("active", True)):
                _raise_409(ShipConfirmErrorCode.CARRIER_NOT_AVAILABLE, "carrier not available")

            provider_name = str(prow.get("name") or "")
            provider_code = str(prow.get("code") or "")

            # 2) provider ∈ warehouse_shipping_providers
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

            # 3) scheme ∈ scheme_warehouses 且有效
            sch_row = (
                await session.execute(
                    text(
                        """
                        SELECT
                          sch.id,
                          sch.shipping_provider_id
                        FROM shipping_provider_pricing_schemes sch
                        JOIN shipping_provider_pricing_scheme_warehouses spsw
                          ON spsw.scheme_id = sch.id
                        WHERE sch.id = :sid
                          AND spsw.warehouse_id = :wid
                          AND spsw.active = true
                          AND sch.active = true
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

            # tracking_no 幂等校验（carrier 维度：以 provider_code 为准）
            tno: Optional[str] = None
            if payload.tracking_no and payload.tracking_no.strip():
                tno = payload.tracking_no.strip()
                dup_tno = (
                    await session.execute(
                        text(
                            """
                            SELECT 1
                              FROM shipping_records
                             WHERE carrier_code = :carrier_code
                               AND tracking_no = :tracking_no
                             LIMIT 1
                            """
                        ),
                        {"carrier_code": provider_code, "tracking_no": tno},
                    )
                ).first()
                if dup_tno:
                    _raise_409(
                        ShipConfirmErrorCode.TRACKING_DUP,
                        "tracking_no already exists for this carrier",
                    )

            # 审计 meta（结构化）
            meta: Dict[str, Any] = {}
            if payload.meta:
                meta.update(payload.meta)

            if payload.carrier_name and payload.carrier_name.strip():
                meta["carrier_name_input"] = payload.carrier_name.strip()

            meta.update(
                {
                    "provider_id": provider_id,
                    "carrier": provider_code,
                    "carrier_name": provider_name,
                    "scheme_id": sid,
                    "warehouse_id": wid,
                }
            )

            if tno:
                meta["tracking_no"] = tno
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

            # Step 1: 写审计事件（成功）
            data = await svc.commit(
                ref=payload.ref,
                platform=payload.platform,
                shop_id=payload.shop_id,
                trace_id=payload.trace_id,
                meta=meta or None,
            )

            json_meta = json.dumps(meta, ensure_ascii=False) if meta else None

            # Step 2: 幂等写 shipping_records（并发安全）
            # 依赖 DB unique: (platform, shop_id, order_ref)
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
                    :error_code,
                    :error_message,
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
                        "weight_kg": None,
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
            ).scalar_one_or_none()

            if inserted is None:
                # 并发/重试导致已存在：幂等返回 409（合同冲突）
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
