# app/tms/shipment/service.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_writer import AuditEventWriter
from app.services.waybill_service import WaybillRequest, WaybillService
from app.tms.quote_snapshot import (
    extract_cost_estimated,
    extract_quote_snapshot,
    validate_quote_snapshot,
)

from .contracts import (
    ConfirmShipmentCommand,
    ConfirmShipmentResult,
    ShipmentApplicationError,
    ShipCommitAuditCommand,
    ShipCommitAuditResult,
    ShipWithWaybillCommand,
    ShipWithWaybillResult,
    UpdateShipmentStatusCommand,
    UpdateShipmentStatusResult,
)


class TransportShipmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ship_commit_audit(
        self,
        command: ShipCommitAuditCommand,
    ) -> ShipCommitAuditResult:
        await self._write_ship_commit_audit(
            ref=command.ref,
            platform=command.platform,
            shop_id=command.shop_id,
            trace_id=command.trace_id,
            meta=command.meta,
        )
        return ShipCommitAuditResult(ok=True, ref=command.ref, trace_id=command.trace_id)

    async def confirm_shipment(
        self,
        command: ConfirmShipmentCommand,
    ) -> ConfirmShipmentResult:
        if command.warehouse_id <= 0:
            self._raise(
                status_code=422,
                code="SHIP_CONFIRM_WAREHOUSE_REQUIRED",
                message="warehouse_id is required",
            )

        if command.shipping_provider_id <= 0:
            self._raise(
                status_code=422,
                code="SHIP_CONFIRM_CARRIER_REQUIRED",
                message="shipping_provider_id is required",
            )

        if command.scheme_id <= 0:
            self._raise(
                status_code=422,
                code="SHIP_CONFIRM_SCHEME_REQUIRED",
                message="scheme_id is required",
            )

        provider = await self._load_active_provider(command.shipping_provider_id)
        provider_code = str(provider["code"] or "")
        provider_name = str(provider["name"] or "")

        await self._ensure_warehouse_binding(
            warehouse_id=command.warehouse_id,
            shipping_provider_id=command.shipping_provider_id,
        )
        await self._ensure_active_scheme_for_warehouse_and_provider(
            scheme_id=command.scheme_id,
            warehouse_id=command.warehouse_id,
            shipping_provider_id=command.shipping_provider_id,
        )

        tracking_no = self._normalized_tracking_no(command.tracking_no)
        if tracking_no is not None:
            await self._ensure_tracking_unique_for_provider(
                shipping_provider_id=command.shipping_provider_id,
                tracking_no=tracking_no,
            )

        meta: dict[str, object] = dict(command.meta or {})
        meta.update(
            {
                "provider_id": command.shipping_provider_id,
                "carrier_code": provider_code,
                "carrier_name": provider_name,
                "scheme_id": command.scheme_id,
                "warehouse_id": command.warehouse_id,
            }
        )

        if command.gross_weight_kg is not None:
            meta["gross_weight_kg"] = float(command.gross_weight_kg)
        if command.packaging_weight_kg is not None:
            meta["packaging_weight_kg"] = float(command.packaging_weight_kg)
        if command.cost_estimated is not None:
            meta["cost_estimated"] = float(command.cost_estimated)
        if command.cost_real is not None:
            meta["cost_real"] = float(command.cost_real)
        if command.delivery_time is not None:
            meta["delivery_time"] = command.delivery_time.isoformat()
        if command.status is not None:
            meta["status"] = command.status
        if command.error_code is not None:
            meta["error_code"] = command.error_code
        if command.error_message is not None:
            meta["error_message"] = command.error_message

        await self._write_ship_commit_audit(
            ref=command.ref,
            platform=command.platform,
            shop_id=command.shop_id,
            trace_id=command.trace_id,
            meta=meta,
        )

        inserted_id = await self._insert_confirm_shipping_record(
            ref=command.ref,
            platform=command.platform,
            shop_id=command.shop_id,
            trace_id=command.trace_id,
            warehouse_id=command.warehouse_id,
            shipping_provider_id=command.shipping_provider_id,
            carrier_code=provider_code,
            carrier_name=provider_name,
            tracking_no=tracking_no,
            meta=meta,
        )

        if inserted_id is None:
            await self.session.rollback()
            self._raise(
                status_code=409,
                code="SHIP_CONFIRM_ORDER_DUP",
                message="order already confirmed",
            )

        await self.session.commit()
        return ConfirmShipmentResult(ok=True, ref=command.ref, trace_id=command.trace_id)

    async def ship_with_waybill(
        self,
        command: ShipWithWaybillCommand,
    ) -> ShipWithWaybillResult:
        quote_snapshot = extract_quote_snapshot(command.meta)
        if not quote_snapshot:
            self._raise(
                status_code=422,
                code="SHIP_WITH_WAYBILL_QUOTE_SNAPSHOT_REQUIRED",
                message="meta.quote_snapshot is required",
            )

        validate_quote_snapshot(quote_snapshot)
        cost_estimated = extract_cost_estimated(quote_snapshot)

        provider = await self._load_active_provider(command.shipping_provider_id)
        provider_code = str(provider["code"] or (command.carrier_code or ""))
        provider_name = str(provider["name"] or (command.carrier_name or ""))

        tracking_no = await self._request_waybill(
            shipping_provider_id=command.shipping_provider_id,
            provider_code=provider_code or None,
            platform=command.platform,
            shop_id=command.shop_id,
            ext_order_no=command.ext_order_no,
            receiver_name=command.receiver_name,
            receiver_phone=command.receiver_phone,
            province=command.province,
            city=command.city,
            district=command.district,
            address_detail=command.address_detail,
            weight_kg=command.weight_kg,
        )

        occurred_at = datetime.now(timezone.utc)
        meta: dict[str, object] = {
            "platform": command.platform.upper(),
            "shop_id": command.shop_id,
            "warehouse_id": int(command.warehouse_id),
            "occurred_at": occurred_at.isoformat(),
            "tracking_no": tracking_no,
            "carrier_code": provider_code,
            "carrier_name": provider_name,
            "shipping_provider_id": int(command.shipping_provider_id),
            "gross_weight_kg": float(command.weight_kg),
            "receiver": {
                "name": command.receiver_name,
                "phone": command.receiver_phone,
                "province": command.province,
                "city": command.city,
                "district": command.district,
                "detail": command.address_detail,
            },
            "waybill_source": "PLATFORM_FAKE",
            "cost_estimated": cost_estimated,
            "quote_snapshot": quote_snapshot,
        }

        await self._write_ship_commit_audit(
            ref=command.order_ref,
            platform=command.platform,
            shop_id=command.shop_id,
            trace_id=command.trace_id,
            meta=meta,
        )

        await self._upsert_waybill_shipping_record(
            order_ref=command.order_ref,
            platform=command.platform,
            shop_id=command.shop_id,
            warehouse_id=command.warehouse_id,
            shipping_provider_id=command.shipping_provider_id,
            carrier_code=provider_code or None,
            carrier_name=provider_name or None,
            tracking_no=tracking_no,
            trace_id=command.trace_id,
            gross_weight_kg=float(command.weight_kg),
            cost_estimated=cost_estimated,
            meta=meta,
        )

        await self.session.commit()

        return ShipWithWaybillResult(
            ok=True,
            ref=command.order_ref,
            tracking_no=tracking_no,
            shipping_provider_id=command.shipping_provider_id,
            carrier_code=provider_code or None,
            carrier_name=provider_name or None,
            status="IN_TRANSIT",
            label_base64=None,
            label_format=None,
        )

    async def update_shipment_status(
        self,
        command: UpdateShipmentStatusCommand,
    ) -> UpdateShipmentStatusResult:
        row = (
            await self.session.execute(
                text(
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
                ),
                {"id": command.record_id},
            )
        ).mappings().first()

        if row is None:
            self._raise(
                status_code=404,
                code="SHIPPING_RECORD_NOT_FOUND",
                message="shipping_record not found",
            )

        order_ref = str(row["order_ref"])
        trace_id = cast(str | None, row.get("trace_id"))
        old_status = cast(str | None, row.get("status"))
        old_delivery_time = cast(datetime | None, row.get("delivery_time"))
        old_meta_raw = row.get("meta")
        old_meta = dict(old_meta_raw) if isinstance(old_meta_raw, dict) else {}
        old_error_code = cast(str | None, row.get("error_code"))
        old_error_message = cast(str | None, row.get("error_message"))

        if command.delivery_time is not None:
            new_delivery_time = command.delivery_time
        elif command.status == "DELIVERED" and old_delivery_time is None:
            new_delivery_time = datetime.now(timezone.utc)
        else:
            new_delivery_time = old_delivery_time

        new_meta: dict[str, object] = dict(old_meta)
        if command.meta:
            new_meta.update(command.meta)
        if command.error_code is not None:
            new_meta["error_code"] = command.error_code
        if command.error_message is not None:
            new_meta["error_message"] = command.error_message

        await self.session.execute(
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
                "id": command.record_id,
                "status": command.status,
                "delivery_time": new_delivery_time,
                "error_code": command.error_code,
                "error_message": command.error_message,
                "meta": self._json_dumps(new_meta),
            },
        )

        try:
            await AuditEventWriter.write(
                self.session,
                flow="OUTBOUND",
                event="SHIP_STATUS_UPDATE",
                ref=order_ref,
                trace_id=trace_id,
                meta={
                    "old_status": old_status,
                    "new_status": command.status,
                    "old_error_code": old_error_code,
                    "old_error_message": old_error_message,
                    "error_code": command.error_code,
                    "error_message": command.error_message,
                    "delivery_time": new_delivery_time.isoformat() if new_delivery_time else None,
                },
                auto_commit=False,
            )
        except Exception:
            pass

        await self.session.commit()

        return UpdateShipmentStatusResult(
            ok=True,
            id=command.record_id,
            status=command.status,
            delivery_time=new_delivery_time,
        )

    async def _load_active_provider(self, shipping_provider_id: int) -> dict[str, object]:
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT id, code, name, active
                    FROM shipping_providers
                    WHERE id = :pid
                    LIMIT 1
                    """
                ),
                {"pid": shipping_provider_id},
            )
        ).mappings().first()

        if not row or not bool(row.get("active", True)):
            self._raise(
                status_code=409,
                code="SHIP_CONFIRM_CARRIER_NOT_AVAILABLE",
                message="carrier not available",
            )

        return dict(row)

    async def _ensure_warehouse_binding(
        self,
        *,
        warehouse_id: int,
        shipping_provider_id: int,
    ) -> None:
        row = (
            await self.session.execute(
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
                {"wid": warehouse_id, "pid": shipping_provider_id},
            )
        ).first()

        if row is None:
            self._raise(
                status_code=409,
                code="SHIP_CONFIRM_CARRIER_NOT_ENABLED_FOR_WAREHOUSE",
                message="carrier not enabled for this warehouse",
            )

    async def _ensure_active_scheme_for_warehouse_and_provider(
        self,
        *,
        scheme_id: int,
        warehouse_id: int,
        shipping_provider_id: int,
    ) -> None:
        row = (
            await self.session.execute(
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
                {"sid": scheme_id, "wid": warehouse_id},
            )
        ).mappings().first()

        if row is None:
            self._raise(
                status_code=409,
                code="SHIP_CONFIRM_SCHEME_NOT_AVAILABLE_FOR_WAREHOUSE",
                message="scheme not available for this warehouse",
            )

        if int(row["shipping_provider_id"]) != shipping_provider_id:
            self._raise(
                status_code=409,
                code="SHIP_CONFIRM_SCHEME_NOT_BELONG_TO_CARRIER",
                message="scheme does not belong to selected carrier",
            )

    async def _ensure_tracking_unique_for_provider(
        self,
        *,
        shipping_provider_id: int,
        tracking_no: str,
    ) -> None:
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT 1
                    FROM shipping_records
                    WHERE shipping_provider_id = :pid
                      AND tracking_no = :tracking_no
                    LIMIT 1
                    """
                ),
                {"pid": shipping_provider_id, "tracking_no": tracking_no},
            )
        ).first()

        if row is not None:
            self._raise(
                status_code=409,
                code="SHIP_CONFIRM_TRACKING_DUP",
                message="tracking_no already exists for this provider",
            )

    async def _write_ship_commit_audit(
        self,
        *,
        ref: str,
        platform: str,
        shop_id: str,
        trace_id: str | None,
        meta: dict[str, object] | None,
    ) -> None:
        payload: dict[str, object] = {
            "platform": platform.upper(),
            "shop_id": shop_id,
        }
        if meta:
            payload.update(meta)

        await AuditEventWriter.write(
            self.session,
            flow="OUTBOUND",
            event="SHIP_COMMIT",
            ref=ref,
            trace_id=trace_id,
            meta=payload,
            auto_commit=False,
        )

    async def _insert_confirm_shipping_record(
        self,
        *,
        ref: str,
        platform: str,
        shop_id: str,
        trace_id: str | None,
        warehouse_id: int,
        shipping_provider_id: int,
        carrier_code: str,
        carrier_name: str,
        tracking_no: str | None,
        meta: dict[str, object],
    ) -> int | None:
        row = await self.session.execute(
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
                    CAST(:meta AS jsonb)
                )
                ON CONFLICT (platform, shop_id, order_ref) DO NOTHING
                RETURNING id
                """
            ),
            {
                "order_ref": ref,
                "platform": platform.upper(),
                "shop_id": shop_id,
                "warehouse_id": warehouse_id,
                "shipping_provider_id": shipping_provider_id,
                "carrier_code": carrier_code,
                "carrier_name": carrier_name,
                "tracking_no": tracking_no,
                "trace_id": trace_id,
                "meta": self._json_dumps(meta),
            },
        )
        return cast(int | None, row.scalar_one_or_none())

    async def _upsert_waybill_shipping_record(
        self,
        *,
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
        await self.session.execute(
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
                    CAST(:meta AS jsonb)
                )
                ON CONFLICT (platform, shop_id, order_ref) DO UPDATE SET
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
                    error_code = EXCLUDED.error_code,
                    error_message = EXCLUDED.error_message,
                    meta = EXCLUDED.meta
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
                "trace_id": trace_id,
                "weight_kg": None,
                "gross_weight_kg": gross_weight_kg,
                "packaging_weight_kg": None,
                "cost_estimated": cost_estimated,
                "cost_real": None,
                "delivery_time": None,
                "status": "IN_TRANSIT",
                "error_code": None,
                "error_message": None,
                "meta": self._json_dumps(meta),
            },
        )

    async def _request_waybill(
        self,
        *,
        shipping_provider_id: int,
        provider_code: str | None,
        platform: str,
        shop_id: str,
        ext_order_no: str,
        receiver_name: str | None,
        receiver_phone: str | None,
        province: str | None,
        city: str | None,
        district: str | None,
        address_detail: str | None,
        weight_kg: float,
    ) -> str:
        waybill_svc = WaybillService()
        req = WaybillRequest(
            shipping_provider_id=shipping_provider_id,
            provider_code=provider_code,
            platform=platform.upper(),
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            receiver={
                "name": receiver_name,
                "phone": receiver_phone,
                "province": province,
                "city": city,
                "district": district,
                "detail": address_detail,
            },
            cargo={"weight_kg": float(weight_kg)},
            extras={},
        )
        result = await waybill_svc.request_waybill(req)
        if not result.ok or not result.tracking_no:
            self._raise(
                status_code=502,
                code="SHIP_WITH_WAYBILL_REQUEST_FAILED",
                message=(
                    f"waybill request failed: "
                    f"{result.error_code or ''} {result.error_message or ''}"
                ).strip(),
            )
        return str(result.tracking_no)

    @staticmethod
    def _normalized_tracking_no(tracking_no: str | None) -> str | None:
        if tracking_no is None:
            return None
        value = tracking_no.strip()
        return value or None

    @staticmethod
    def _json_dumps(meta: dict[str, object]) -> str:
        return json.dumps(meta, ensure_ascii=False)

    @staticmethod
    def _raise(*, status_code: int, code: str, message: str) -> None:
        raise ShipmentApplicationError(
            status_code=status_code,
            code=code,
            message=message,
        )
