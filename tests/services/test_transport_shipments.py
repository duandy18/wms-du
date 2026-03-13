# tests/services/test_transport_shipments.py
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.tms.shipment import (
    ShipmentApplicationError,
    ShipWithWaybillCommand,
    TransportShipmentService,
    UpdateShipmentStatusCommand,
)
from app.tms.quote_snapshot import extract_cost_estimated

pytestmark = pytest.mark.asyncio


def _build_quote_snapshot(*, provider_id: int, total_amount: float = 12.5) -> dict[str, object]:
    return {
        "version": "v1",
        "source": "shipping_quote.calc",
        "input": {
            "warehouse_id": 1,
            "provider_id": provider_id,
        },
        "selected_quote": {
            "quote_status": "OK",
            "scheme_id": 1,
            "scheme_name": "UT-SCHEME-1",
            "provider_id": provider_id,
            "carrier_code": "UT-CAR-1",
            "carrier_name": "UT-CARRIER-1",
            "currency": "CNY",
            "total_amount": total_amount,
            "weight": {"billable_weight_kg": 1.2},
            "destination_group": {"name": "华北测试组"},
            "pricing_matrix": {"range_id": 1},
            "breakdown": {"base": total_amount},
            "reasons": ["matrix_match:ut", f"total={total_amount:.2f} CNY"],
        },
    }


async def _load_transport_and_record(
    session: AsyncSession,
    *,
    order_ref: str,
    platform: str,
    shop_id: str,
) -> tuple[dict[str, object], dict[str, object]]:
    shipment_row = (
        await session.execute(
            text(
                """
                SELECT
                  id,
                  order_ref,
                  platform,
                  shop_id,
                  warehouse_id,
                  shipping_provider_id,
                  quote_snapshot,
                  tracking_no,
                  carrier_code,
                  carrier_name,
                  status,
                  delivery_time,
                  error_code,
                  error_message
                FROM transport_shipments
                WHERE platform = :platform
                  AND shop_id = :shop_id
                  AND order_ref = :order_ref
                LIMIT 1
                """
            ),
            {
                "platform": platform.upper(),
                "shop_id": shop_id,
                "order_ref": order_ref,
            },
        )
    ).mappings().first()

    record_row = (
        await session.execute(
            text(
                """
                SELECT
                  id,
                  shipment_id,
                  order_ref,
                  platform,
                  shop_id,
                  warehouse_id,
                  shipping_provider_id,
                  tracking_no,
                  carrier_code,
                  carrier_name,
                  cost_estimated,
                  status,
                  delivery_time,
                  error_code,
                  error_message,
                  meta
                FROM shipping_records
                WHERE platform = :platform
                  AND shop_id = :shop_id
                  AND order_ref = :order_ref
                LIMIT 1
                """
            ),
            {
                "platform": platform.upper(),
                "shop_id": shop_id,
                "order_ref": order_ref,
            },
        )
    ).mappings().first()

    assert shipment_row is not None, "transport_shipments row not found"
    assert record_row is not None, "shipping_records row not found"
    return dict(shipment_row), dict(record_row)


async def _create_in_transit_shipment(
    session: AsyncSession,
    *,
    suffix: str,
) -> tuple[TransportShipmentService, str, str, str, int]:
    svc = TransportShipmentService(session)
    uniq = uuid4().hex[:10]
    platform = "PDD"
    shop_id = "1"
    ext_order_no = f"{suffix}-{uniq}"
    order_ref = f"ORD:{platform}:{shop_id}:{ext_order_no}"

    await svc.ship_with_waybill(
        ShipWithWaybillCommand(
            order_ref=order_ref,
            trace_id=f"TRACE-{uniq}",
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            warehouse_id=1,
            shipping_provider_id=1,
            carrier_code=None,
            carrier_name=None,
            weight_kg=2.0,
            receiver_name="测试用户",
            receiver_phone="13600000000",
            province="北京市",
            city="北京市",
            district="西城区",
            address_detail="测试地址 9 号",
            quote_snapshot=_build_quote_snapshot(provider_id=1, total_amount=18.8),
            meta={"source": "state-machine-test"},
        )
    )

    _, record = await _load_transport_and_record(
        session,
        order_ref=order_ref,
        platform=platform,
        shop_id=shop_id,
    )
    return svc, order_ref, platform, shop_id, int(record["id"])


async def test_ship_with_waybill_writes_transport_shipment_and_projection(session: AsyncSession) -> None:
    svc = TransportShipmentService(session)
    uniq = uuid4().hex[:10]
    platform = "PDD"
    shop_id = "1"
    ext_order_no = f"EXT-{uniq}"
    order_ref = f"ORD:{platform}:{shop_id}:{ext_order_no}"
    trace_id = f"TRACE-{uniq}"

    result = await svc.ship_with_waybill(
        ShipWithWaybillCommand(
            order_ref=order_ref,
            trace_id=trace_id,
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            warehouse_id=1,
            shipping_provider_id=1,
            carrier_code=None,
            carrier_name=None,
            weight_kg=1.25,
            receiver_name="张三",
            receiver_phone="13800000000",
            province="北京市",
            city="北京市",
            district="朝阳区",
            address_detail="测试地址 1 号",
            quote_snapshot=_build_quote_snapshot(provider_id=1, total_amount=12.5),
            meta={"source": "unit-test"},
        )
    )

    assert result.ok is True
    assert result.ref == order_ref
    assert result.shipping_provider_id == 1
    assert result.status == "IN_TRANSIT"
    assert result.tracking_no == f"P1-{ext_order_no}"

    shipment, record = await _load_transport_and_record(
        session,
        order_ref=order_ref,
        platform=platform,
        shop_id=shop_id,
    )

    assert int(shipment["id"]) > 0
    assert int(record["shipment_id"]) == int(shipment["id"])
    assert str(shipment["tracking_no"]) == str(record["tracking_no"]) == f"P1-{ext_order_no}"
    assert int(shipment["shipping_provider_id"]) == int(record["shipping_provider_id"]) == 1
    assert str(shipment["carrier_code"]) == str(record["carrier_code"]) == "UT-CAR-1"
    assert str(shipment["carrier_name"]) == str(record["carrier_name"]) == "UT-CARRIER-1"
    assert str(shipment["status"]) == str(record["status"]) == "IN_TRANSIT"

    quote_snapshot = shipment["quote_snapshot"]
    assert isinstance(quote_snapshot, dict)
    assert extract_cost_estimated(quote_snapshot) == float(record["cost_estimated"])


async def test_ship_with_waybill_rejects_provider_not_bound_to_warehouse(session: AsyncSession) -> None:
    svc = TransportShipmentService(session)
    uniq = uuid4().hex[:10]
    platform = "PDD"
    shop_id = "1"
    ext_order_no = f"EXT-NOBIND-{uniq}"
    order_ref = f"ORD:{platform}:{shop_id}:{ext_order_no}"

    with pytest.raises(ShipmentApplicationError) as exc_info:
        await svc.ship_with_waybill(
            ShipWithWaybillCommand(
                order_ref=order_ref,
                trace_id=f"TRACE-{uniq}",
                platform=platform,
                shop_id=shop_id,
                ext_order_no=ext_order_no,
                warehouse_id=1,
                shipping_provider_id=2,  # base_seed 中 provider=2 未绑定 warehouse=1
                carrier_code=None,
                carrier_name=None,
                weight_kg=1.0,
                receiver_name="李四",
                receiver_phone="13900000000",
                province="北京市",
                city="北京市",
                district="海淀区",
                address_detail="测试地址 2 号",
                quote_snapshot=_build_quote_snapshot(provider_id=2, total_amount=9.9),
                meta=None,
            )
        )

    err = exc_info.value
    assert err.status_code == 409
    assert err.code == "SHIP_WITH_WAYBILL_CARRIER_NOT_ENABLED_FOR_WAREHOUSE"


async def test_ship_with_waybill_rejects_quote_snapshot_provider_mismatch(session: AsyncSession) -> None:
    svc = TransportShipmentService(session)
    uniq = uuid4().hex[:10]
    platform = "PDD"
    shop_id = "1"
    ext_order_no = f"EXT-MISMATCH-{uniq}"
    order_ref = f"ORD:{platform}:{shop_id}:{ext_order_no}"

    with pytest.raises(ShipmentApplicationError) as exc_info:
        await svc.ship_with_waybill(
            ShipWithWaybillCommand(
                order_ref=order_ref,
                trace_id=f"TRACE-{uniq}",
                platform=platform,
                shop_id=shop_id,
                ext_order_no=ext_order_no,
                warehouse_id=1,
                shipping_provider_id=1,
                carrier_code=None,
                carrier_name=None,
                weight_kg=1.0,
                receiver_name="王五",
                receiver_phone="13700000000",
                province="北京市",
                city="北京市",
                district="东城区",
                address_detail="测试地址 3 号",
                quote_snapshot=_build_quote_snapshot(provider_id=2, total_amount=10.1),
                meta=None,
            )
        )

    err = exc_info.value
    assert err.status_code == 422
    assert err.code == "SHIP_WITH_WAYBILL_QUOTE_PROVIDER_MISMATCH"


async def test_update_shipment_status_syncs_projection_and_transport_shipment(session: AsyncSession) -> None:
    svc = TransportShipmentService(session)
    uniq = uuid4().hex[:10]
    platform = "PDD"
    shop_id = "1"
    ext_order_no = f"EXT-STATUS-{uniq}"
    order_ref = f"ORD:{platform}:{shop_id}:{ext_order_no}"

    await svc.ship_with_waybill(
        ShipWithWaybillCommand(
            order_ref=order_ref,
            trace_id=f"TRACE-{uniq}",
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            warehouse_id=1,
            shipping_provider_id=1,
            carrier_code=None,
            carrier_name=None,
            weight_kg=2.0,
            receiver_name="赵六",
            receiver_phone="13600000000",
            province="北京市",
            city="北京市",
            district="西城区",
            address_detail="测试地址 4 号",
            quote_snapshot=_build_quote_snapshot(provider_id=1, total_amount=18.8),
            meta={"source": "status-sync-test"},
        )
    )

    shipment, record = await _load_transport_and_record(
        session,
        order_ref=order_ref,
        platform=platform,
        shop_id=shop_id,
    )
    record_id = int(record["id"])
    shipment_id = int(shipment["id"])
    delivered_at = datetime.now(timezone.utc)

    result = await svc.update_shipment_status(
        UpdateShipmentStatusCommand(
            record_id=record_id,
            status="DELIVERED",
            delivery_time=delivered_at,
            error_code=None,
            error_message=None,
            meta={"sync_case": "delivered"},
        )
    )

    assert result.ok is True
    assert result.id == record_id
    assert result.status == "DELIVERED"
    assert result.delivery_time == delivered_at

    shipment_row = (
        await session.execute(
            text(
                """
                SELECT status, delivery_time, error_code, error_message
                FROM transport_shipments
                WHERE id = :id
                """
            ),
            {"id": shipment_id},
        )
    ).mappings().first()
    assert shipment_row is not None
    assert shipment_row["status"] == "DELIVERED"
    assert shipment_row["delivery_time"] == delivered_at
    assert shipment_row["error_code"] is None
    assert shipment_row["error_message"] is None

    record_row = (
        await session.execute(
            text(
                """
                SELECT status, delivery_time, error_code, error_message, meta
                FROM shipping_records
                WHERE id = :id
                """
            ),
            {"id": record_id},
        )
    ).mappings().first()
    assert record_row is not None
    assert record_row["status"] == "DELIVERED"
    assert record_row["delivery_time"] == delivered_at
    assert record_row["error_code"] is None
    assert record_row["error_message"] is None
    assert isinstance(record_row["meta"], dict)
    assert record_row["meta"]["sync_case"] == "delivered"


async def test_update_shipment_status_allows_in_transit_to_lost(session: AsyncSession) -> None:
    svc, order_ref, platform, shop_id, record_id = await _create_in_transit_shipment(
        session,
        suffix="EXT-LOST",
    )

    result = await svc.update_shipment_status(
        UpdateShipmentStatusCommand(
            record_id=record_id,
            status="LOST",
            delivery_time=None,
            error_code="CARRIER_LOST",
            error_message="carrier reported lost package",
            meta={"sync_case": "lost"},
        )
    )

    assert result.ok is True
    assert result.id == record_id
    assert result.status == "LOST"
    assert result.delivery_time is None

    shipment_row, record_row = await _load_transport_and_record(
        session,
        order_ref=order_ref,
        platform=platform,
        shop_id=shop_id,
    )

    assert shipment_row["status"] == "LOST"
    assert shipment_row["error_code"] == "CARRIER_LOST"
    assert shipment_row["error_message"] == "carrier reported lost package"

    assert record_row["status"] == "LOST"
    assert record_row["error_code"] == "CARRIER_LOST"
    assert record_row["error_message"] == "carrier reported lost package"
    assert isinstance(record_row["meta"], dict)
    assert record_row["meta"]["sync_case"] == "lost"
    assert record_row["meta"]["error_code"] == "CARRIER_LOST"
    assert record_row["meta"]["error_message"] == "carrier reported lost package"


async def test_update_shipment_status_allows_in_transit_to_returned(session: AsyncSession) -> None:
    svc, order_ref, platform, shop_id, record_id = await _create_in_transit_shipment(
        session,
        suffix="EXT-RETURNED",
    )

    result = await svc.update_shipment_status(
        UpdateShipmentStatusCommand(
            record_id=record_id,
            status="RETURNED",
            delivery_time=None,
            error_code="BUYER_REJECTED",
            error_message="buyer rejected package",
            meta={"sync_case": "returned"},
        )
    )

    assert result.ok is True
    assert result.id == record_id
    assert result.status == "RETURNED"
    assert result.delivery_time is None

    shipment_row, record_row = await _load_transport_and_record(
        session,
        order_ref=order_ref,
        platform=platform,
        shop_id=shop_id,
    )

    assert shipment_row["status"] == "RETURNED"
    assert shipment_row["error_code"] == "BUYER_REJECTED"
    assert shipment_row["error_message"] == "buyer rejected package"

    assert record_row["status"] == "RETURNED"
    assert record_row["error_code"] == "BUYER_REJECTED"
    assert record_row["error_message"] == "buyer rejected package"
    assert isinstance(record_row["meta"], dict)
    assert record_row["meta"]["sync_case"] == "returned"
    assert record_row["meta"]["error_code"] == "BUYER_REJECTED"
    assert record_row["meta"]["error_message"] == "buyer rejected package"


async def test_update_shipment_status_rejects_delivered_to_lost(session: AsyncSession) -> None:
    svc, _, _, _, record_id = await _create_in_transit_shipment(
        session,
        suffix="EXT-DELIVERED-TO-LOST",
    )

    delivered_at = datetime.now(timezone.utc)
    await svc.update_shipment_status(
        UpdateShipmentStatusCommand(
            record_id=record_id,
            status="DELIVERED",
            delivery_time=delivered_at,
            error_code=None,
            error_message=None,
            meta={"sync_case": "delivered-first"},
        )
    )

    with pytest.raises(ShipmentApplicationError) as exc_info:
        await svc.update_shipment_status(
            UpdateShipmentStatusCommand(
                record_id=record_id,
                status="LOST",
                delivery_time=None,
                error_code="POST_DELIVERY_LOST",
                error_message="invalid transition after delivered",
                meta={"sync_case": "lost-after-delivered"},
            )
        )

    err = exc_info.value
    assert err.status_code == 409
    assert err.code == "SHIPMENT_STATUS_TRANSITION_INVALID"


async def test_update_shipment_status_rejects_returned_to_delivered(session: AsyncSession) -> None:
    svc, _, _, _, record_id = await _create_in_transit_shipment(
        session,
        suffix="EXT-RETURNED-TO-DELIVERED",
    )

    await svc.update_shipment_status(
        UpdateShipmentStatusCommand(
            record_id=record_id,
            status="RETURNED",
            delivery_time=None,
            error_code="BUYER_REJECTED",
            error_message="returned first",
            meta={"sync_case": "returned-first"},
        )
    )

    with pytest.raises(ShipmentApplicationError) as exc_info:
        await svc.update_shipment_status(
            UpdateShipmentStatusCommand(
                record_id=record_id,
                status="DELIVERED",
                delivery_time=datetime.now(timezone.utc),
                error_code=None,
                error_message=None,
                meta={"sync_case": "delivered-after-returned"},
            )
        )

    err = exc_info.value
    assert err.status_code == 409
    assert err.code == "SHIPMENT_STATUS_TRANSITION_INVALID"


async def test_update_shipment_status_rejects_unknown_status_value(session: AsyncSession) -> None:
    svc, _, _, _, record_id = await _create_in_transit_shipment(
        session,
        suffix="EXT-UNKNOWN-STATUS",
    )

    with pytest.raises(ShipmentApplicationError) as exc_info:
        await svc.update_shipment_status(
            UpdateShipmentStatusCommand(
                record_id=record_id,
                status="UNKNOWN",
                delivery_time=None,
                error_code=None,
                error_message=None,
                meta={"sync_case": "unknown-status"},
            )
        )

    err = exc_info.value
    assert err.status_code == 422
    assert err.code == "SHIPMENT_STATUS_INVALID"


async def test_shipping_record_db_forbids_null_shipment_id(session: AsyncSession) -> None:
    uniq = uuid4().hex[:10]
    order_ref = f"ORD:PDD:1:NULL-SHIPMENT-{uniq}"

    with pytest.raises(IntegrityError):
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
                    status,
                    meta
                )
                VALUES (
                    :order_ref,
                    'PDD',
                    '1',
                    NULL,
                    1,
                    1,
                    'STO',
                    '申通快递',
                    :tracking_no,
                    :trace_id,
                    'IN_TRANSIT',
                    CAST(:meta AS jsonb)
                )
                """
            ),
            {
                "order_ref": order_ref,
                "tracking_no": f"MANUAL-{uniq}",
                "trace_id": f"TRACE-{uniq}",
                "meta": '{"case":"db-not-null"}',
            },
        )
        await session.commit()

    await session.rollback()
