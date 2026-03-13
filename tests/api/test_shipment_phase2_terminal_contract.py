# tests/api/test_shipment_phase2_terminal_contract.py
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.tms.shipment import ShipWithWaybillCommand, TransportShipmentService

pytestmark = pytest.mark.asyncio


async def _login_headers(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/users/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    assert token
    return {"Authorization": f"Bearer {token}"}


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


async def _create_waybill_shipment_via_service(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
    trace_id: str,
) -> str:
    order_ref = f"ORD:{platform}:{shop_id}:{ext_order_no}"
    svc = TransportShipmentService(session)

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
            weight_kg=2.3,
            receiver_name="张三",
            receiver_phone="13800000000",
            province="北京市",
            city="北京市",
            district="朝阳区",
            address_detail="测试地址 88 号",
            quote_snapshot=_build_quote_snapshot(provider_id=1, total_amount=15.6),
            meta={"source": "api-terminal-test"},
        )
    )
    assert result.ok is True
    assert result.ref == order_ref
    return order_ref


async def _load_shipping_record_id(
    session: AsyncSession,
    *,
    order_ref: str,
    platform: str,
    shop_id: str,
) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT id
                FROM shipping_records
                WHERE order_ref = :order_ref
                  AND platform = :platform
                  AND shop_id = :shop_id
                LIMIT 1
                """
            ),
            {
                "order_ref": order_ref,
                "platform": platform.upper(),
                "shop_id": shop_id,
            },
        )
    ).first()
    assert row is not None, "shipping_record not found"
    return int(row[0])


async def test_ship_confirm_route_is_removed(client: AsyncClient) -> None:
    headers = await _login_headers(client)

    resp = await client.post(
        "/ship/confirm",
        headers=headers,
        json={
            "ref": "ORD:PDD:1:LEGACY-CONFIRM-001",
            "platform": "PDD",
            "shop_id": "1",
            "warehouse_id": 1,
            "shipping_provider_id": 1,
            "scheme_id": 1,
        },
    )

    assert resp.status_code == 404, resp.text


async def test_shipping_record_status_api_syncs_projection_and_transport_shipment(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_headers(client)

    uniq = uuid4().hex[:10]
    platform = "PDD"
    shop_id = "1"
    ext_order_no = f"API-SHIP-{uniq}"
    trace_id = f"TRACE-{uniq}"

    order_ref = await _create_waybill_shipment_via_service(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        trace_id=trace_id,
    )

    record_id = await _load_shipping_record_id(
        session,
        order_ref=order_ref,
        platform=platform,
        shop_id=shop_id,
    )

    delivered_at = datetime.now(timezone.utc).replace(microsecond=0)

    update_resp = await client.post(
        f"/shipping-records/{record_id}/status",
        headers=headers,
        json={
            "status": "DELIVERED",
            "delivery_time": delivered_at.isoformat(),
            "error_code": None,
            "error_message": None,
            "meta": {"api_case": "phase2-terminal"},
        },
    )
    assert update_resp.status_code == 200, update_resp.text

    body = update_resp.json()
    assert body["ok"] is True
    assert int(body["id"]) == record_id
    assert body["status"] == "DELIVERED"

    record_row = (
        await session.execute(
            text(
                """
                SELECT
                  shipment_id,
                  status,
                  delivery_time,
                  error_code,
                  error_message,
                  meta
                FROM shipping_records
                WHERE id = :id
                """
            ),
            {"id": record_id},
        )
    ).mappings().first()
    assert record_row is not None
    assert record_row["shipment_id"] is not None
    assert record_row["status"] == "DELIVERED"
    assert record_row["delivery_time"] == delivered_at
    assert record_row["error_code"] is None
    assert record_row["error_message"] is None
    assert isinstance(record_row["meta"], dict)
    assert record_row["meta"]["api_case"] == "phase2-terminal"

    shipment_row = (
        await session.execute(
            text(
                """
                SELECT
                  id,
                  status,
                  delivery_time,
                  error_code,
                  error_message
                FROM transport_shipments
                WHERE id = :id
                """
            ),
            {"id": int(record_row["shipment_id"])},
        )
    ).mappings().first()
    assert shipment_row is not None
    assert shipment_row["status"] == "DELIVERED"
    assert shipment_row["delivery_time"] == delivered_at
    assert shipment_row["error_code"] is None
    assert shipment_row["error_message"] is None
