# tests/services/test_transport_shipments.py
from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.tms.quote_snapshot import (
    extract_cost_estimated,
    extract_freight_estimated,
    extract_surcharge_estimated,
)
from app.tms.shipment import (
    ShipmentApplicationError,
    ShipWithWaybillCommand,
    TransportShipmentService,
)
from tests.services.pick._seed_orders import insert_min_order
from tests.utils.ensure_minimal import ensure_warehouse

pytestmark = pytest.mark.asyncio


def _build_quote_snapshot(
    *,
    provider_id: int,
    warehouse_id: int = 1,
    total_amount: float = 12.5,
) -> dict[str, object]:
    base_amount = round(float(total_amount) - 1.5, 2)
    surcharge_amount = round(float(total_amount) - base_amount, 2)
    return {
        "version": "v1",
        "source": "shipping_quote.calc",
        "input": {
            "warehouse_id": warehouse_id,
            "provider_id": provider_id,
        },
        "selected_quote": {
            "quote_status": "OK",
            "template_id": 1,
            "template_name": "UT-TEMPLATE-1",
            "provider_id": provider_id,
            "carrier_code": "UT-CAR-1",
            "carrier_name": "UT-CARRIER-1",
            "currency": "CNY",
            "total_amount": total_amount,
            "weight": {"billable_weight_kg": 1.25},
            "destination_group": {"name": "华北测试组"},
            "pricing_matrix": {"range_id": 1},
            "breakdown": {
                "base": {
                    "amount": base_amount,
                },
                "surcharges": [
                    {
                        "id": 1,
                        "name": "测试附加费",
                        "scope": "city",
                        "amount": surcharge_amount,
                        "detail": {"kind": "unit-test"},
                    }
                ],
                "summary": {
                    "base_amount": base_amount,
                    "surcharge_amount": surcharge_amount,
                    "extra_amount": surcharge_amount,
                    "total_amount": total_amount,
                },
            },
            "reasons": ["matrix_match:ut", f"total={total_amount:.2f} CNY"],
        },
    }


async def _pick_existing_binding(
    session: AsyncSession,
) -> dict[str, int]:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  wsp.warehouse_id,
                  wsp.shipping_provider_id
                FROM warehouse_shipping_providers wsp
                JOIN shipping_providers sp
                  ON sp.id = wsp.shipping_provider_id
                WHERE COALESCE(wsp.active, TRUE) = TRUE
                ORDER BY wsp.warehouse_id ASC, wsp.shipping_provider_id ASC
                LIMIT 1
                """
            )
        )
    ).mappings().first()

    assert row is not None, "no active warehouse/provider binding found for shipment tests"
    return {
        "warehouse_id": int(row["warehouse_id"]),
        "provider_id": int(row["shipping_provider_id"]),
    }


async def _seed_prepare_package_case(
    session: AsyncSession,
    *,
    package_no: int = 1,
    weight_kg: float = 1.25,
    total_amount: float = 12.5,
) -> dict[str, object]:
    uniq = uuid4().hex[:10]
    platform = "PDD"
    shop_id = "1"
    ext_order_no = f"SHIP-UT-{uniq}"
    trace_id = f"TRACE-{uniq}"

    binding = await _pick_existing_binding(session)
    warehouse_id = int(binding["warehouse_id"])
    provider_id = int(binding["provider_id"])

    await ensure_warehouse(session, id=warehouse_id, name=f"WH-{warehouse_id}")

    order_id = await insert_min_order(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        warehouse_id=warehouse_id,
        fulfillment_status="SERVICE_ASSIGNED",
        status="CREATED",
        trace_id=trace_id,
    )

    await session.execute(
        text(
            """
            INSERT INTO order_address (
                order_id,
                receiver_name,
                receiver_phone,
                province,
                city,
                district,
                detail
            )
            VALUES (
                :order_id,
                '张三',
                '13800000000',
                '北京市',
                '北京市',
                '朝阳区',
                '测试地址 1 号'
            )
            ON CONFLICT (order_id) DO UPDATE
               SET receiver_name = EXCLUDED.receiver_name,
                   receiver_phone = EXCLUDED.receiver_phone,
                   province = EXCLUDED.province,
                   city = EXCLUDED.city,
                   district = EXCLUDED.district,
                   detail = EXCLUDED.detail
            """
        ),
        {"order_id": int(order_id)},
    )

    await session.execute(
        text(
            """
            INSERT INTO order_shipment_prepare (
                order_id,
                address_ready_status,
                package_status,
                pricing_status,
                provider_status
            )
            VALUES (
                :order_id,
                'ready',
                'planned',
                'calculated',
                'selected'
            )
            ON CONFLICT (order_id) DO UPDATE
               SET address_ready_status = EXCLUDED.address_ready_status,
                   package_status = EXCLUDED.package_status,
                   pricing_status = EXCLUDED.pricing_status,
                   provider_status = EXCLUDED.provider_status
            """
        ),
        {"order_id": int(order_id)},
    )

    quote_snapshot = _build_quote_snapshot(
        provider_id=provider_id,
        warehouse_id=warehouse_id,
        total_amount=total_amount,
    )

    await session.execute(
        text(
            """
            INSERT INTO order_shipment_prepare_packages (
                order_id,
                package_no,
                weight_kg,
                warehouse_id,
                pricing_status,
                selected_provider_id,
                selected_quote_snapshot,
                created_at,
                updated_at
            )
            VALUES (
                :order_id,
                :package_no,
                :weight_kg,
                :warehouse_id,
                'calculated',
                :provider_id,
                CAST(:quote_snapshot AS jsonb),
                now(),
                now()
            )
            ON CONFLICT (order_id, package_no) DO UPDATE
               SET weight_kg = EXCLUDED.weight_kg,
                   warehouse_id = EXCLUDED.warehouse_id,
                   pricing_status = EXCLUDED.pricing_status,
                   selected_provider_id = EXCLUDED.selected_provider_id,
                   selected_quote_snapshot = EXCLUDED.selected_quote_snapshot,
                   updated_at = now()
            """
        ),
        {
            "order_id": int(order_id),
            "package_no": int(package_no),
            "weight_kg": float(weight_kg),
            "warehouse_id": warehouse_id,
            "provider_id": provider_id,
            "quote_snapshot": json.dumps(quote_snapshot, ensure_ascii=False),
        },
    )

    await _upsert_active_waybill_config(
        session,
        platform=platform,
        shop_id=shop_id,
        provider_id=provider_id,
    )

    await session.commit()

    return {
        "order_id": int(order_id),
        "platform": platform,
        "shop_id": shop_id,
        "ext_order_no": ext_order_no,
        "package_no": int(package_no),
        "warehouse_id": warehouse_id,
        "provider_id": provider_id,
        "order_ref": f"ORD:{platform}:{shop_id}:{ext_order_no}",
        "quote_snapshot": quote_snapshot,
    }


async def _upsert_active_waybill_config(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    provider_id: int,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO electronic_waybill_configs (
                platform,
                shop_id,
                shipping_provider_id,
                customer_code,
                sender_name,
                sender_mobile,
                sender_phone,
                sender_province,
                sender_city,
                sender_district,
                sender_address,
                active,
                created_at,
                updated_at
            )
            VALUES (
                :platform,
                :shop_id,
                :provider_id,
                'UT-CUSTOMER-CODE',
                '张三',
                '13800000000',
                NULL,
                '北京市',
                '北京市',
                '朝阳区',
                '测试发件地址 1 号',
                TRUE,
                now(),
                now()
            )
            ON CONFLICT (platform, shop_id, shipping_provider_id) DO UPDATE
               SET customer_code = EXCLUDED.customer_code,
                   sender_name = EXCLUDED.sender_name,
                   sender_mobile = EXCLUDED.sender_mobile,
                   sender_phone = EXCLUDED.sender_phone,
                   sender_province = EXCLUDED.sender_province,
                   sender_city = EXCLUDED.sender_city,
                   sender_district = EXCLUDED.sender_district,
                   sender_address = EXCLUDED.sender_address,
                   active = TRUE,
                   updated_at = now()
            """
        ),
        {
            "platform": str(platform).upper(),
            "shop_id": str(shop_id),
            "provider_id": int(provider_id),
        },
    )


async def _upsert_prepare_row_ready(
    session: AsyncSession,
    *,
    order_id: int,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO order_shipment_prepare (
                order_id,
                address_ready_status,
                package_status,
                pricing_status,
                provider_status
            )
            VALUES (
                :order_id,
                'ready',
                'planned',
                'calculated',
                'selected'
            )
            ON CONFLICT (order_id) DO UPDATE SET
                address_ready_status = EXCLUDED.address_ready_status,
                package_status = EXCLUDED.package_status,
                pricing_status = EXCLUDED.pricing_status,
                provider_status = EXCLUDED.provider_status
            """
        ),
        {"order_id": int(order_id)},
    )


async def _mark_package_ready(
    session: AsyncSession,
    *,
    order_id: int,
    package_no: int,
    warehouse_id: int,
    provider_id: int,
    weight_kg: float = 1.25,
    total_amount: float = 12.5,
) -> dict[str, object]:
    quote_snapshot = _build_quote_snapshot(
        provider_id=provider_id,
        warehouse_id=warehouse_id,
        total_amount=total_amount,
    )

    await _upsert_prepare_row_ready(session, order_id=order_id)

    await session.execute(
        text(
            """
            UPDATE order_shipment_prepare_packages
               SET weight_kg = :weight_kg,
                   warehouse_id = :warehouse_id,
                   pricing_status = 'calculated',
                   selected_provider_id = :provider_id,
                   selected_quote_snapshot = CAST(:quote_snapshot AS jsonb),
                   updated_at = now()
             WHERE order_id = :order_id
               AND package_no = :package_no
            """
        ),
        {
            "order_id": int(order_id),
            "package_no": int(package_no),
            "weight_kg": float(weight_kg),
            "warehouse_id": int(warehouse_id),
            "provider_id": int(provider_id),
            "quote_snapshot": json.dumps(quote_snapshot, ensure_ascii=False),
        },
    )
    return quote_snapshot


async def _clear_package_provider(
    session: AsyncSession,
    *,
    order_id: int,
    package_no: int,
) -> None:
    await session.execute(
        text(
            """
            UPDATE order_shipment_prepare_packages
               SET selected_provider_id = NULL,
                   updated_at = now()
             WHERE order_id = :order_id
               AND package_no = :package_no
            """
        ),
        {
            "order_id": int(order_id),
            "package_no": int(package_no),
        },
    )


async def _clear_package_weight(
    session: AsyncSession,
    *,
    order_id: int,
    package_no: int,
) -> None:
    await session.execute(
        text(
            """
            UPDATE order_shipment_prepare_packages
               SET weight_kg = NULL,
                   updated_at = now()
             WHERE order_id = :order_id
               AND package_no = :package_no
            """
        ),
        {
            "order_id": int(order_id),
            "package_no": int(package_no),
        },
    )


async def _clear_package_quote_snapshot(
    session: AsyncSession,
    *,
    order_id: int,
    package_no: int,
) -> None:
    await session.execute(
        text(
            """
            UPDATE order_shipment_prepare_packages
               SET selected_quote_snapshot = NULL,
                   updated_at = now()
             WHERE order_id = :order_id
               AND package_no = :package_no
            """
        ),
        {
            "order_id": int(order_id),
            "package_no": int(package_no),
        },
    )


async def _set_package_pricing_status(
    session: AsyncSession,
    *,
    order_id: int,
    package_no: int,
    pricing_status: str,
) -> None:
    await session.execute(
        text(
            """
            UPDATE order_shipment_prepare_packages
               SET pricing_status = :pricing_status,
                   updated_at = now()
             WHERE order_id = :order_id
               AND package_no = :package_no
            """
        ),
        {
            "order_id": int(order_id),
            "package_no": int(package_no),
            "pricing_status": str(pricing_status),
        },
    )


async def _set_prepare_address_ready_status(
    session: AsyncSession,
    *,
    order_id: int,
    address_ready_status: str,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO order_shipment_prepare (
                order_id,
                address_ready_status,
                package_status,
                pricing_status,
                provider_status
            )
            VALUES (
                :order_id,
                :address_ready_status,
                'planned',
                'calculated',
                'selected'
            )
            ON CONFLICT (order_id) DO UPDATE SET
                address_ready_status = EXCLUDED.address_ready_status,
                package_status = EXCLUDED.package_status,
                pricing_status = EXCLUDED.pricing_status,
                provider_status = EXCLUDED.provider_status
            """
        ),
        {
            "order_id": int(order_id),
            "address_ready_status": str(address_ready_status),
        },
    )


async def _load_shipping_record(
    session: AsyncSession,
    *,
    order_ref: str,
    platform: str,
    shop_id: str,
    package_no: int,
) -> dict[str, object]:
    record_row = (
        await session.execute(
            text(
                """
                SELECT
                  id,
                  order_ref,
                  platform,
                  shop_id,
                  package_no,
                  warehouse_id,
                  shipping_provider_id,
                  tracking_no,
                  carrier_code,
                  carrier_name,
                  freight_estimated,
                  surcharge_estimated,
                  cost_estimated,
                  gross_weight_kg,
                  length_cm,
                  width_cm,
                  height_cm,
                  sender,
                  dest_province,
                  dest_city
                FROM shipping_records
                WHERE platform = :platform
                  AND shop_id = :shop_id
                  AND order_ref = :order_ref
                  AND package_no = :package_no
                LIMIT 1
                """
            ),
            {
                "platform": platform.upper(),
                "shop_id": shop_id,
                "order_ref": order_ref,
                "package_no": int(package_no),
            },
        )
    ).mappings().first()

    assert record_row is not None, "shipping_records row not found"
    return dict(record_row)


async def _count_shipping_records(
    session: AsyncSession,
    *,
    order_ref: str,
    platform: str,
    shop_id: str,
    package_no: int,
) -> int:
    value = (
        await session.execute(
            text(
                """
                SELECT COUNT(*) AS n
                FROM shipping_records
                WHERE platform = :platform
                  AND shop_id = :shop_id
                  AND order_ref = :order_ref
                  AND package_no = :package_no
                """
            ),
            {
                "platform": platform.upper(),
                "shop_id": shop_id,
                "order_ref": order_ref,
                "package_no": int(package_no),
            },
        )
    ).scalar_one()
    return int(value)


async def test_ship_with_waybill_writes_shipping_record_ledger_at_package_grain(
    session: AsyncSession,
) -> None:
    svc = TransportShipmentService(session)
    ctx = await _seed_prepare_package_case(session)

    quote_snapshot = await _mark_package_ready(
        session,
        order_id=int(ctx["order_id"]),
        package_no=int(ctx["package_no"]),
        warehouse_id=int(ctx["warehouse_id"]),
        provider_id=int(ctx["provider_id"]),
        weight_kg=1.25,
        total_amount=12.5,
    )

    result = await svc.ship_with_waybill(
        ShipWithWaybillCommand(
            order_ref=str(ctx["order_ref"]),
            trace_id=f"TRACE-{uuid4().hex[:10]}",
            platform=str(ctx["platform"]),
            shop_id=str(ctx["shop_id"]),
            ext_order_no=str(ctx["ext_order_no"]),
            package_no=int(ctx["package_no"]),
            receiver_name="张三",
            receiver_phone="13800000000",
            province="北京市",
            city="北京市",
            district="朝阳区",
            address_detail="测试地址 1 号",
            meta={"source": "unit-test"},
        )
    )

    assert result.ok is True
    assert result.ref == str(ctx["order_ref"])
    assert result.package_no == int(ctx["package_no"])
    assert result.shipping_provider_id == int(ctx["provider_id"])
    assert result.status == "IN_TRANSIT"
    assert result.tracking_no is not None
    assert result.tracking_no.startswith(f"P{int(ctx['provider_id'])}-{ctx['ext_order_no']}-")

    record = await _load_shipping_record(
        session,
        order_ref=str(ctx["order_ref"]),
        platform=str(ctx["platform"]),
        shop_id=str(ctx["shop_id"]),
        package_no=int(ctx["package_no"]),
    )

    assert int(record["id"]) > 0
    assert int(record["package_no"]) == int(ctx["package_no"])
    assert str(record["tracking_no"]).startswith(
        f"P{int(ctx['provider_id'])}-{ctx['ext_order_no']}-"
    )
    assert int(record["warehouse_id"]) == int(ctx["warehouse_id"])
    assert int(record["shipping_provider_id"]) == int(ctx["provider_id"])
    assert str(record["carrier_code"]) == "UT-CAR-1"
    assert str(record["carrier_name"]) == "UT-CARRIER-1"
    assert float(record["gross_weight_kg"]) == pytest.approx(1.25)
    assert record["length_cm"] is None
    assert record["width_cm"] is None
    assert record["height_cm"] is None
    assert str(record["sender"]) == "张三"
    assert str(record["dest_province"]) == "北京市"
    assert str(record["dest_city"]) == "北京市"

    assert extract_freight_estimated(quote_snapshot) == float(record["freight_estimated"])
    assert extract_surcharge_estimated(quote_snapshot) == float(record["surcharge_estimated"])
    assert extract_cost_estimated(quote_snapshot) == float(record["cost_estimated"])


async def test_ship_with_waybill_is_idempotent_per_order_ref_and_package_no(
    session: AsyncSession,
) -> None:
    svc = TransportShipmentService(session)
    ctx = await _seed_prepare_package_case(session)

    await _mark_package_ready(
        session,
        order_id=int(ctx["order_id"]),
        package_no=int(ctx["package_no"]),
        warehouse_id=int(ctx["warehouse_id"]),
        provider_id=int(ctx["provider_id"]),
        weight_kg=1.25,
        total_amount=12.5,
    )

    command = ShipWithWaybillCommand(
        order_ref=str(ctx["order_ref"]),
        trace_id=f"TRACE-{uuid4().hex[:10]}",
        platform=str(ctx["platform"]),
        shop_id=str(ctx["shop_id"]),
        ext_order_no=str(ctx["ext_order_no"]),
        package_no=int(ctx["package_no"]),
        receiver_name="张三",
        receiver_phone="13800000000",
        province="北京市",
        city="北京市",
        district="朝阳区",
        address_detail="测试地址 1 号",
        meta={"source": "unit-test"},
    )

    result1 = await svc.ship_with_waybill(command)
    result2 = await svc.ship_with_waybill(command)

    assert result1.ok is True
    assert result2.ok is True
    assert result1.package_no == int(ctx["package_no"])
    assert result2.package_no == int(ctx["package_no"])
    assert result1.tracking_no == result2.tracking_no

    count = await _count_shipping_records(
        session,
        order_ref=str(ctx["order_ref"]),
        platform=str(ctx["platform"]),
        shop_id=str(ctx["shop_id"]),
        package_no=int(ctx["package_no"]),
    )
    assert count == 1


async def test_ship_with_waybill_rejects_package_not_found(session: AsyncSession) -> None:
    svc = TransportShipmentService(session)
    ctx = await _seed_prepare_package_case(session)

    with pytest.raises(ShipmentApplicationError) as exc_info:
        await svc.ship_with_waybill(
            ShipWithWaybillCommand(
                order_ref=str(ctx["order_ref"]),
                trace_id=f"TRACE-{uuid4().hex[:10]}",
                platform=str(ctx["platform"]),
                shop_id=str(ctx["shop_id"]),
                ext_order_no=str(ctx["ext_order_no"]),
                package_no=999999,
                receiver_name="李四",
                receiver_phone="13900000000",
                province="北京市",
                city="北京市",
                district="海淀区",
                address_detail="测试地址 2 号",
                meta=None,
            )
        )

    err = exc_info.value
    assert err.status_code == 404
    assert "package_no=999999 not found" in err.message


async def test_ship_with_waybill_rejects_when_selected_provider_missing(
    session: AsyncSession,
) -> None:
    svc = TransportShipmentService(session)
    ctx = await _seed_prepare_package_case(session)

    await _mark_package_ready(
        session,
        order_id=int(ctx["order_id"]),
        package_no=int(ctx["package_no"]),
        warehouse_id=int(ctx["warehouse_id"]),
        provider_id=int(ctx["provider_id"]),
        weight_kg=1.25,
        total_amount=12.5,
    )
    await _clear_package_provider(
        session,
        order_id=int(ctx["order_id"]),
        package_no=int(ctx["package_no"]),
    )

    with pytest.raises(ShipmentApplicationError) as exc_info:
        await svc.ship_with_waybill(
            ShipWithWaybillCommand(
                order_ref=str(ctx["order_ref"]),
                trace_id=f"TRACE-{uuid4().hex[:10]}",
                platform=str(ctx["platform"]),
                shop_id=str(ctx["shop_id"]),
                ext_order_no=str(ctx["ext_order_no"]),
                package_no=int(ctx["package_no"]),
                receiver_name="王五",
                receiver_phone="13700000000",
                province="北京市",
                city="北京市",
                district="东城区",
                address_detail="测试地址 3 号",
                meta=None,
            )
        )

    err = exc_info.value
    assert err.status_code in {409, 422}
    assert "selected_provider_id" in err.message or "provider" in err.message.lower()


async def test_ship_with_waybill_rejects_when_weight_missing(
    session: AsyncSession,
) -> None:
    svc = TransportShipmentService(session)
    ctx = await _seed_prepare_package_case(session)

    await _mark_package_ready(
        session,
        order_id=int(ctx["order_id"]),
        package_no=int(ctx["package_no"]),
        warehouse_id=int(ctx["warehouse_id"]),
        provider_id=int(ctx["provider_id"]),
        weight_kg=1.25,
        total_amount=12.5,
    )
    await _clear_package_weight(
        session,
        order_id=int(ctx["order_id"]),
        package_no=int(ctx["package_no"]),
    )

    with pytest.raises(ShipmentApplicationError) as exc_info:
        await svc.ship_with_waybill(
            ShipWithWaybillCommand(
                order_ref=str(ctx["order_ref"]),
                trace_id=f"TRACE-{uuid4().hex[:10]}",
                platform=str(ctx["platform"]),
                shop_id=str(ctx["shop_id"]),
                ext_order_no=str(ctx["ext_order_no"]),
                package_no=int(ctx["package_no"]),
                receiver_name="赵六",
                receiver_phone="13600000000",
                province="北京市",
                city="北京市",
                district="西城区",
                address_detail="测试地址 4 号",
                meta=None,
            )
        )

    err = exc_info.value
    assert err.status_code in {409, 422}
    assert "weight" in err.message.lower()


async def test_ship_with_waybill_rejects_when_quote_snapshot_missing(
    session: AsyncSession,
) -> None:
    svc = TransportShipmentService(session)
    ctx = await _seed_prepare_package_case(session)

    await _mark_package_ready(
        session,
        order_id=int(ctx["order_id"]),
        package_no=int(ctx["package_no"]),
        warehouse_id=int(ctx["warehouse_id"]),
        provider_id=int(ctx["provider_id"]),
        weight_kg=1.25,
        total_amount=12.5,
    )
    await _clear_package_quote_snapshot(
        session,
        order_id=int(ctx["order_id"]),
        package_no=int(ctx["package_no"]),
    )

    with pytest.raises(ShipmentApplicationError) as exc_info:
        await svc.ship_with_waybill(
            ShipWithWaybillCommand(
                order_ref=str(ctx["order_ref"]),
                trace_id=f"TRACE-{uuid4().hex[:10]}",
                platform=str(ctx["platform"]),
                shop_id=str(ctx["shop_id"]),
                ext_order_no=str(ctx["ext_order_no"]),
                package_no=int(ctx["package_no"]),
                receiver_name="钱七",
                receiver_phone="13500000000",
                province="北京市",
                city="北京市",
                district="丰台区",
                address_detail="测试地址 5 号",
                meta=None,
            )
        )

    err = exc_info.value
    assert err.status_code in {409, 422}
    assert "quote" in err.message.lower()


async def test_ship_with_waybill_rejects_when_pricing_not_calculated(
    session: AsyncSession,
) -> None:
    svc = TransportShipmentService(session)
    ctx = await _seed_prepare_package_case(session)

    await _mark_package_ready(
        session,
        order_id=int(ctx["order_id"]),
        package_no=int(ctx["package_no"]),
        warehouse_id=int(ctx["warehouse_id"]),
        provider_id=int(ctx["provider_id"]),
        weight_kg=1.25,
        total_amount=12.5,
    )
    await _set_package_pricing_status(
        session,
        order_id=int(ctx["order_id"]),
        package_no=int(ctx["package_no"]),
        pricing_status="pending",
    )

    with pytest.raises(ShipmentApplicationError) as exc_info:
        await svc.ship_with_waybill(
            ShipWithWaybillCommand(
                order_ref=str(ctx["order_ref"]),
                trace_id=f"TRACE-{uuid4().hex[:10]}",
                platform=str(ctx["platform"]),
                shop_id=str(ctx["shop_id"]),
                ext_order_no=str(ctx["ext_order_no"]),
                package_no=int(ctx["package_no"]),
                receiver_name="孙八",
                receiver_phone="13400000000",
                province="北京市",
                city="北京市",
                district="石景山区",
                address_detail="测试地址 6 号",
                meta=None,
            )
        )

    err = exc_info.value
    assert err.status_code in {409, 422}
    assert "pricing" in err.message.lower() or "calculated" in err.message.lower()


async def test_ship_with_waybill_rejects_when_address_not_ready(
    session: AsyncSession,
) -> None:
    svc = TransportShipmentService(session)
    ctx = await _seed_prepare_package_case(session)

    await _mark_package_ready(
        session,
        order_id=int(ctx["order_id"]),
        package_no=int(ctx["package_no"]),
        warehouse_id=int(ctx["warehouse_id"]),
        provider_id=int(ctx["provider_id"]),
        weight_kg=1.25,
        total_amount=12.5,
    )
    await _set_prepare_address_ready_status(
        session,
        order_id=int(ctx["order_id"]),
        address_ready_status="pending",
    )

    with pytest.raises(ShipmentApplicationError) as exc_info:
        await svc.ship_with_waybill(
            ShipWithWaybillCommand(
                order_ref=str(ctx["order_ref"]),
                trace_id=f"TRACE-{uuid4().hex[:10]}",
                platform=str(ctx["platform"]),
                shop_id=str(ctx["shop_id"]),
                ext_order_no=str(ctx["ext_order_no"]),
                package_no=int(ctx["package_no"]),
                receiver_name="周九",
                receiver_phone="13300000000",
                province="北京市",
                city="北京市",
                district="通州区",
                address_detail="测试地址 7 号",
                meta=None,
            )
        )

    err = exc_info.value
    assert err.status_code in {409, 422}
    assert "address" in err.message.lower() or "ready" in err.message.lower()


async def test_shipping_record_accepts_current_terminal_columns_with_package_no(
    session: AsyncSession,
) -> None:
    uniq = uuid4().hex[:10]
    order_ref = f"ORD:PDD:1:TERMINAL-COLS-{uniq}"

    await session.execute(
        text(
            """
            INSERT INTO shipping_records (
                order_ref,
                platform,
                shop_id,
                package_no,
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
                'PDD',
                '1',
                1,
                1,
                1,
                'STO',
                '申通快递',
                :tracking_no,
                1.230,
                10.00,
                2.50,
                12.50,
                73.03,
                44.55,
                8.40,
                '张三',
                '北京市',
                '北京市'
            )
            """
        ),
        {
            "order_ref": order_ref,
            "tracking_no": f"MANUAL-{uniq}",
        },
    )
    await session.commit()

    row = (
        await session.execute(
            text(
                """
                SELECT
                  order_ref,
                  platform,
                  shop_id,
                  package_no,
                  warehouse_id,
                  shipping_provider_id,
                  tracking_no,
                  freight_estimated,
                  surcharge_estimated,
                  cost_estimated,
                  length_cm,
                  width_cm,
                  height_cm,
                  sender
                FROM shipping_records
                WHERE order_ref = :order_ref
                  AND package_no = 1
                LIMIT 1
                """
            ),
            {"order_ref": order_ref},
        )
    ).mappings().first()

    assert row is not None
    assert row["order_ref"] == order_ref
    assert row["platform"] == "PDD"
    assert row["shop_id"] == "1"
    assert int(row["package_no"]) == 1
    assert int(row["warehouse_id"]) == 1
    assert int(row["shipping_provider_id"]) == 1
    assert float(row["freight_estimated"]) == pytest.approx(10.00)
    assert float(row["surcharge_estimated"]) == pytest.approx(2.50)
    assert float(row["cost_estimated"]) == pytest.approx(12.50)
    assert float(row["length_cm"]) == pytest.approx(73.03)
    assert float(row["width_cm"]) == pytest.approx(44.55)
    assert float(row["height_cm"]) == pytest.approx(8.40)
    assert str(row["sender"]) == "张三"

    await session.rollback()
