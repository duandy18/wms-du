# app/tms/shipment/service.py
# 分拆说明：
# - 本文件已从“单文件大而全”结构拆分为“应用编排层”。
# - SQL 持久化已下沉到 repository.py；
# - 前置校验已下沉到 validators.py；
# - 面单请求边界已下沉到 waybill_gateway.py。
# - Shipment 状态双写规则已下沉到 status_sync.py。
# - Shipment 审计写入已下沉到 audit.py。
# - 本文件当前只负责：应用流程编排、事务提交、结果组装。
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.tms.quote_snapshot import extract_cost_estimated, validate_quote_snapshot

from .audit import (
    write_ship_commit_audit,
    write_ship_status_update_audit,
)
from .contracts import (
    ShipmentApplicationError,
    ShipCommitAuditCommand,
    ShipCommitAuditResult,
    ShipWithWaybillCommand,
    ShipWithWaybillResult,
    UpdateShipmentStatusCommand,
    UpdateShipmentStatusResult,
)
from .repository import (
    upsert_transport_shipment_for_waybill,
    upsert_waybill_shipping_record,
)
from .status_sync import apply_shipment_status_update
from .validators import (
    ensure_quote_snapshot_provider_matches,
    ensure_warehouse_binding,
    load_active_provider,
)
from .waybill_gateway import request_waybill


class TransportShipmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ship_commit_audit(
        self,
        command: ShipCommitAuditCommand,
    ) -> ShipCommitAuditResult:
        await write_ship_commit_audit(
            self.session,
            ref=command.ref,
            platform=command.platform,
            shop_id=command.shop_id,
            trace_id=command.trace_id,
            meta=command.meta,
        )
        return ShipCommitAuditResult(ok=True, ref=command.ref, trace_id=command.trace_id)

    async def ship_with_waybill(
        self,
        command: ShipWithWaybillCommand,
    ) -> ShipWithWaybillResult:
        quote_snapshot = dict(command.quote_snapshot) if isinstance(command.quote_snapshot, dict) else {}
        if not quote_snapshot:
            self._raise(
                status_code=422,
                code="SHIP_WITH_WAYBILL_QUOTE_SNAPSHOT_REQUIRED",
                message="quote_snapshot is required",
            )

        validate_quote_snapshot(quote_snapshot)
        ensure_quote_snapshot_provider_matches(
            quote_snapshot,
            shipping_provider_id=command.shipping_provider_id,
        )
        cost_estimated = extract_cost_estimated(quote_snapshot)

        provider = await load_active_provider(self.session, command.shipping_provider_id)
        provider_code = str(provider["code"] or (command.carrier_code or ""))
        provider_name = str(provider["name"] or (command.carrier_name or ""))

        await ensure_warehouse_binding(
            self.session,
            warehouse_id=command.warehouse_id,
            shipping_provider_id=command.shipping_provider_id,
        )

        tracking_no = await request_waybill(
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
        meta: dict[str, object] = dict(command.meta or {})
        meta.pop("quote_snapshot", None)
        meta.update(
            {
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
        )

        shipment_id = await upsert_transport_shipment_for_waybill(
            self.session,
            order_ref=command.order_ref,
            platform=command.platform,
            shop_id=command.shop_id,
            trace_id=command.trace_id,
            warehouse_id=command.warehouse_id,
            shipping_provider_id=command.shipping_provider_id,
            quote_snapshot=quote_snapshot,
            weight_kg=float(command.weight_kg),
            receiver_name=command.receiver_name,
            receiver_phone=command.receiver_phone,
            province=command.province,
            city=command.city,
            district=command.district,
            address_detail=command.address_detail,
            tracking_no=tracking_no,
            carrier_code=provider_code or None,
            carrier_name=provider_name or None,
            status="IN_TRANSIT",
            delivery_time=None,
            error_code=None,
            error_message=None,
        )

        await write_ship_commit_audit(
            self.session,
            ref=command.order_ref,
            platform=command.platform,
            shop_id=command.shop_id,
            trace_id=command.trace_id,
            meta=meta,
        )

        await upsert_waybill_shipping_record(
            self.session,
            shipment_id=shipment_id,
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
        applied = await apply_shipment_status_update(
            self.session,
            record_id=command.record_id,
            status=command.status,
            delivery_time=command.delivery_time,
            error_code=command.error_code,
            error_message=command.error_message,
            meta=dict(command.meta or {}),
        )

        try:
            await write_ship_status_update_audit(
                self.session,
                ref=applied.order_ref,
                trace_id=applied.trace_id,
                old_status=applied.old_status,
                new_status=applied.status,
                delivery_time=applied.delivery_time,
                old_error_code=applied.old_error_code,
                old_error_message=applied.old_error_message,
                error_code=command.error_code,
                error_message=command.error_message,
            )
        except Exception:
            pass

        await self.session.commit()

        return UpdateShipmentStatusResult(
            ok=True,
            id=applied.record_id,
            status=applied.status,
            delivery_time=applied.delivery_time,
        )

    @staticmethod
    def _raise(*, status_code: int, code: str, message: str) -> None:
        raise ShipmentApplicationError(
            status_code=status_code,
            code=code,
            message=message,
        )
