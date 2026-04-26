# app/shipping_assist/shipment/service.py
# 分拆说明：
# - 本文件当前只保留 Shipment 执行域应用编排。
# - ShippingRecord 当前语义已收口为“物流台帐表”；
# - transport_shipments 仍未物理删除，但本文件不再把 shipping_records 绑定为其 projection；
# - 物流状态写链路已删除，平台状态不再回写运输账本。
# - 当前 ship_with_waybill 已收口为“包级 authority”：
#   1) 前端只传 package_no 与地址/审计补充信息
#   2) 仓库 / 承运商 / 重量 / 报价快照 一律以后端 order_shipment_prepare_packages 真相为准
# - 发运准备阶段能力已拆到：
#   - service_prepare_orders.py
#   - service_prepare_packages.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shipping_assist.shipment.models.order_shipment_prepare import OrderShipmentPrepare
from app.shipping_assist.shipment.models.order_shipment_prepare_package import OrderShipmentPreparePackage
from app.shipping_assist.quote_snapshot import (
    extract_cost_estimated,
    extract_freight_estimated,
    extract_surcharge_estimated,
    validate_quote_snapshot,
)

from .audit import write_ship_commit_audit
from .contracts import (
    ShipmentApplicationError,
    ShipCommitAuditCommand,
    ShipCommitAuditResult,
    ShipWithWaybillCommand,
    ShipWithWaybillResult,
)
from .repository import get_waybill_shipping_record, upsert_waybill_shipping_record
from .repository_waybill_config import get_active_waybill_config_for_shipment
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
        order_id = await self._load_order_id(
            platform=command.platform,
            shop_id=command.shop_id,
            ext_order_no=command.ext_order_no,
        )

        package = await self.session.scalar(
            select(OrderShipmentPreparePackage).where(
                OrderShipmentPreparePackage.order_id == order_id,
                OrderShipmentPreparePackage.package_no == int(command.package_no),
            )
        )
        if package is None:
            self._raise(
                status_code=404,
                code="SHIP_WITH_WAYBILL_PACKAGE_NOT_FOUND",
                message=f"package_no={int(command.package_no)} not found for this order",
            )

        prepare = await self.session.scalar(
            select(OrderShipmentPrepare).where(OrderShipmentPrepare.order_id == order_id)
        )
        if prepare is None:
            self._raise(
                status_code=409,
                code="SHIP_WITH_WAYBILL_PREPARE_REQUIRED",
                message="shipment prepare record is required before requesting waybill",
            )

        if str(prepare.address_ready_status or "pending") != "ready":
            self._raise(
                status_code=409,
                code="SHIP_WITH_WAYBILL_ADDRESS_NOT_READY",
                message="address_ready_status must be ready before requesting waybill",
            )

        if package.weight_kg is None or float(package.weight_kg) <= 0:
            self._raise(
                status_code=409,
                code="SHIP_WITH_WAYBILL_PACKAGE_WEIGHT_REQUIRED",
                message="package weight_kg is required before requesting waybill",
            )

        if str(package.pricing_status or "pending") != "calculated":
            self._raise(
                status_code=409,
                code="SHIP_WITH_WAYBILL_PACKAGE_PRICING_NOT_READY",
                message="package pricing_status must be calculated before requesting waybill",
            )

        if package.selected_provider_id is None:
            self._raise(
                status_code=409,
                code="SHIP_WITH_WAYBILL_PACKAGE_PROVIDER_REQUIRED",
                message="package selected_provider_id is required before requesting waybill",
            )

        quote_snapshot = (
            dict(package.selected_quote_snapshot)
            if isinstance(package.selected_quote_snapshot, dict)
            else {}
        )
        if not quote_snapshot:
            self._raise(
                status_code=409,
                code="SHIP_WITH_WAYBILL_PACKAGE_QUOTE_SNAPSHOT_REQUIRED",
                message="package selected_quote_snapshot is required before requesting waybill",
            )

        if package.warehouse_id is None:
            self._raise(
                status_code=409,
                code="SHIP_WITH_WAYBILL_PACKAGE_WAREHOUSE_REQUIRED",
                message="package warehouse_id is required before requesting waybill",
            )

        validate_quote_snapshot(quote_snapshot)
        ensure_quote_snapshot_provider_matches(
            quote_snapshot,
            shipping_provider_id=int(package.selected_provider_id),
        )

        freight_estimated = extract_freight_estimated(quote_snapshot)
        surcharge_estimated = extract_surcharge_estimated(quote_snapshot)
        cost_estimated = extract_cost_estimated(quote_snapshot)

        provider = await load_active_provider(
            self.session,
            int(package.selected_provider_id),
        )
        shipping_provider_code = str(provider["shipping_provider_code"] or "")
        provider_name = str(provider["name"] or "")
        company_code = str(provider.get("company_code") or "").strip() or None

        await ensure_warehouse_binding(
            self.session,
            warehouse_id=int(package.warehouse_id),
            shipping_provider_id=int(package.selected_provider_id),
        )

        waybill_config = await get_active_waybill_config_for_shipment(
            self.session,
            platform=command.platform,
            shop_id=command.shop_id,
            shipping_provider_id=int(package.selected_provider_id),
        )
        if waybill_config is None:
            self._raise(
                status_code=409,
                code="SHIP_WITH_WAYBILL_CONFIG_REQUIRED",
                message="current shop has no active electronic waybill config for this shipping provider",
            )

        sender: dict[str, Any] = {
            "name": waybill_config.sender_name,
            "mobile": waybill_config.sender_mobile,
            "phone": waybill_config.sender_phone,
            "province": waybill_config.sender_province,
            "city": waybill_config.sender_city,
            "district": waybill_config.sender_district,
            "address": waybill_config.sender_address,
        }

        existing_record = await get_waybill_shipping_record(
            self.session,
            order_ref=command.order_ref,
            platform=command.platform,
            shop_id=command.shop_id,
            package_no=int(package.package_no),
        )
        if existing_record is not None:
            return ShipWithWaybillResult(
                ok=True,
                ref=command.order_ref,
                package_no=int(package.package_no),
                tracking_no=str(existing_record["tracking_no"]),
                shipping_provider_id=int(existing_record["shipping_provider_id"]),
                shipping_provider_code=(
                    str(existing_record["shipping_provider_code"])
                    if existing_record["shipping_provider_code"] is not None
                    else None
                ),
                shipping_provider_name=(
                    str(existing_record["shipping_provider_name"])
                    if existing_record["shipping_provider_name"] is not None
                    else None
                ),
                status="IN_TRANSIT",
                print_data=None,
                template_url=None,
            )

        result = await request_waybill(
            shipping_provider_id=int(package.selected_provider_id),
            shipping_provider_code=shipping_provider_code or None,
            company_code=company_code,
            customer_code=waybill_config.customer_code,
            platform=command.platform,
            shop_id=command.shop_id,
            ext_order_no=command.ext_order_no,
            package_no=int(package.package_no),
            sender=sender,
            receiver_name=command.receiver_name,
            receiver_phone=command.receiver_phone,
            province=command.province,
            city=command.city,
            district=command.district,
            address_detail=command.address_detail,
            weight_kg=float(package.weight_kg),
        )
        tracking_no = str(result.tracking_no)

        occurred_at = datetime.now(timezone.utc)
        audit_meta: dict[str, object] = dict(command.meta or {})
        audit_meta.update(
            {
                "platform": command.platform.upper(),
                "shop_id": command.shop_id,
                "package_no": int(package.package_no),
                "warehouse_id": int(package.warehouse_id),
                "occurred_at": occurred_at.isoformat(),
                "tracking_no": tracking_no,
                "shipping_provider_code": shipping_provider_code or None,
                "shipping_provider_name": provider_name or None,
                "shipping_provider_id": int(package.selected_provider_id),
                "gross_weight_kg": float(package.weight_kg),
                "freight_estimated": freight_estimated,
                "surcharge_estimated": surcharge_estimated,
                "cost_estimated": cost_estimated,
                "dest_province": command.province,
                "dest_city": command.city,
                "sender": sender,
                "receiver": {
                    "name": command.receiver_name,
                    "phone": command.receiver_phone,
                    "province": command.province,
                    "city": command.city,
                    "district": command.district,
                    "detail": command.address_detail,
                },
                "waybill_source": result.source or "UNKNOWN",
                "selected_quote_snapshot": quote_snapshot,
            }
        )

        await write_ship_commit_audit(
            self.session,
            ref=command.order_ref,
            platform=command.platform,
            shop_id=command.shop_id,
            trace_id=command.trace_id,
            meta=audit_meta,
        )

        await upsert_waybill_shipping_record(
            self.session,
            order_ref=command.order_ref,
            platform=command.platform,
            shop_id=command.shop_id,
            package_no=int(package.package_no),
            warehouse_id=int(package.warehouse_id),
            shipping_provider_id=int(package.selected_provider_id),
            shipping_provider_code=shipping_provider_code or None,
            shipping_provider_name=provider_name or None,
            tracking_no=tracking_no,
            sender=str(sender.get("name") or "") or None,
            gross_weight_kg=float(package.weight_kg),
            freight_estimated=freight_estimated,
            surcharge_estimated=surcharge_estimated,
            cost_estimated=cost_estimated,
            length_cm=None,
            width_cm=None,
            height_cm=None,
            dest_province=command.province,
            dest_city=command.city,
        )

        await self.session.commit()

        return ShipWithWaybillResult(
            ok=True,
            ref=command.order_ref,
            package_no=int(package.package_no),
            tracking_no=tracking_no,
            shipping_provider_id=int(package.selected_provider_id),
            shipping_provider_code=shipping_provider_code or None,
            shipping_provider_name=provider_name or None,
            status="IN_TRANSIT",
            print_data=result.print_data,
            template_url=result.template_url,
        )

    async def _load_order_id(
        self,
        *,
        platform: str,
        shop_id: str,
        ext_order_no: str,
    ) -> int:
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT id
                    FROM orders
                    WHERE platform = :platform
                      AND shop_id = :shop_id
                      AND ext_order_no = :ext_order_no
                    LIMIT 1
                    """
                ),
                {
                    "platform": str(platform or "").strip().upper(),
                    "shop_id": str(shop_id or "").strip(),
                    "ext_order_no": str(ext_order_no or "").strip(),
                },
            )
        ).mappings().first()

        if row is None:
            self._raise(
                status_code=404,
                code="SHIP_WITH_WAYBILL_ORDER_NOT_FOUND",
                message="order not found",
            )
        return int(row["id"])

    @staticmethod
    def _raise(*, status_code: int, code: str, message: str) -> None:
        raise ShipmentApplicationError(
            status_code=status_code,
            code=code,
            message=message,
        )
