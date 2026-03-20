# tests/services/test_transport_shipments.py
from __future__ import annotations

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

pytestmark = pytest.mark.asyncio


def _build_quote_snapshot(*, provider_id: int, total_amount: float = 12.5) -> dict[str, object]:
    base_amount = round(float(total_amount) - 1.5, 2)
    surcharge_amount = round(float(total_amount) - base_amount, 2)
    return {
        "version": "v1",
        "source": "shipping_quote.calc",
        "input": {
            "warehouse_id": 1,
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
            "weight": {"billable_weight_kg": 1.2},
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


async def _load_shipping_record(
    session: AsyncSession,
    *,
    order_ref: str,
    platform: str,
    shop_id: str,
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

    assert record_row is not None, "shipping_records row not found"
    return dict(record_row)


async def test_ship_with_waybill_writes_shipping_record_ledger(session: AsyncSession) -> None:
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
            length_cm=73.03,
            width_cm=44.55,
            height_cm=8.40,
            sender="张三",
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

    record = await _load_shipping_record(
        session,
        order_ref=order_ref,
        platform=platform,
        shop_id=shop_id,
    )

    assert int(record["id"]) > 0
    assert str(record["tracking_no"]) == f"P1-{ext_order_no}"
    assert int(record["shipping_provider_id"]) == 1
    assert str(record["carrier_code"]) == "UT-CAR-1"
    assert str(record["carrier_name"]) == "UT-CARRIER-1"
    assert float(record["gross_weight_kg"]) == pytest.approx(1.25)
    assert float(record["length_cm"]) == pytest.approx(73.03)
    assert float(record["width_cm"]) == pytest.approx(44.55)
    assert float(record["height_cm"]) == pytest.approx(8.40)
    assert str(record["sender"]) == "张三"
    assert str(record["dest_province"]) == "北京市"
    assert str(record["dest_city"]) == "北京市"

    quote_snapshot = _build_quote_snapshot(provider_id=1, total_amount=12.5)
    assert extract_freight_estimated(quote_snapshot) == float(record["freight_estimated"])
    assert extract_surcharge_estimated(quote_snapshot) == float(record["surcharge_estimated"])
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
                shipping_provider_id=2,
                carrier_code=None,
                carrier_name=None,
                weight_kg=1.0,
                length_cm=None,
                width_cm=None,
                height_cm=None,
                sender=None,
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
                length_cm=None,
                width_cm=None,
                height_cm=None,
                sender=None,
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


async def test_shipping_record_accepts_current_terminal_columns(session: AsyncSession) -> None:
    uniq = uuid4().hex[:10]
    order_ref = f"ORD:PDD:1:TERMINAL-COLS-{uniq}"

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
                'PDD',
                '1',
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
