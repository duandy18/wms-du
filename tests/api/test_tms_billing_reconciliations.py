from __future__ import annotations

from decimal import Decimal
from typing import Dict

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _login_headers(client) -> Dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json().get("access_token")
    assert isinstance(token, str) and token
    return {"Authorization": f"Bearer {token}"}


async def _pick_shipping_provider_id(session: AsyncSession) -> int:
    row = await session.execute(text("SELECT id FROM shipping_providers ORDER BY id ASC LIMIT 1"))
    provider_id = row.scalar_one_or_none()
    assert provider_id is not None, "shipping_providers baseline seed missing"
    return int(provider_id)


async def _pick_warehouse_id(session: AsyncSession) -> int:
    row = await session.execute(text("SELECT id FROM warehouses ORDER BY id ASC LIMIT 1"))
    warehouse_id = row.scalar_one_or_none()
    assert warehouse_id is not None, "warehouses baseline seed missing"
    return int(warehouse_id)


async def _insert_carrier_bill_item(
    session: AsyncSession,
    *,
    shipping_provider_code: str,
    tracking_no: str,
    billing_weight_kg: Decimal | None = None,
    freight_amount: Decimal | None = None,
    surcharge_amount: Decimal | None = None,
    total_amount: Decimal | None = None,
) -> int:
    row = await session.execute(
        text(
            """
            INSERT INTO carrier_bill_items (
                shipping_provider_code,
                bill_month,
                tracking_no,
                business_time,
                destination_province,
                destination_city,
                billing_weight_kg,
                freight_amount,
                surcharge_amount,
                total_amount,
                settlement_object,
                order_customer,
                sender_name,
                network_name,
                size_text,
                parent_customer,
                raw_payload
            )
            VALUES (
                :shipping_provider_code,
                :bill_month,
                :tracking_no,
                now(),
                'UT-PROV',
                'UT-CITY',
                :billing_weight_kg,
                :freight_amount,
                :surcharge_amount,
                :total_amount,
                'UT-SETTLEMENT',
                'UT-CUSTOMER',
                'UT-SENDER',
                'UT-NETWORK',
                '10x10x10',
                'UT-PARENT',
                '{}'::jsonb
            )
            RETURNING id
            """
        ),
        {
            "shipping_provider_code": shipping_provider_code,
            "bill_month": "2026-03",
            "tracking_no": tracking_no,
            "billing_weight_kg": billing_weight_kg,
            "freight_amount": freight_amount,
            "surcharge_amount": surcharge_amount,
            "total_amount": total_amount,
        },
    )
    bill_item_id = row.scalar_one_or_none()
    assert bill_item_id is not None
    return int(bill_item_id)


async def _insert_shipping_record(
    session: AsyncSession,
    *,
    shipping_provider_code: str,
    tracking_no: str,
    gross_weight_kg: Decimal | None = None,
    cost_estimated: Decimal | None = None,
) -> int:
    warehouse_id = await _pick_warehouse_id(session)
    shipping_provider_id = await _pick_shipping_provider_id(session)

    row = await session.execute(
        text(
            """
            INSERT INTO shipping_records (
                order_ref,
                platform,
                store_code,
                package_no,
                shipping_provider_code,
                cost_estimated,
                shipping_provider_name,
                tracking_no,
                gross_weight_kg,
                warehouse_id,
                shipping_provider_id,
                dest_province,
                dest_city,
                freight_estimated,
                surcharge_estimated,
                length_cm,
                width_cm,
                height_cm,
                sender
            )
            VALUES (
                :order_ref,
                'PDD',
                '1',
                1,
                :shipping_provider_code,
                :cost_estimated,
                'UT-CARRIER',
                :tracking_no,
                :gross_weight_kg,
                :warehouse_id,
                :shipping_provider_id,
                'UT-PROV',
                'UT-CITY',
                NULL,
                NULL,
                NULL,
                NULL,
                NULL,
                'UT-SENDER'
            )
            RETURNING id
            """
        ),
        {
            "order_ref": f"UT-ORDER-{tracking_no}",
            "shipping_provider_code": shipping_provider_code,
            "cost_estimated": cost_estimated,
            "tracking_no": tracking_no,
            "gross_weight_kg": gross_weight_kg,
            "warehouse_id": warehouse_id,
            "shipping_provider_id": shipping_provider_id,
        },
    )
    shipping_record_id = row.scalar_one_or_none()
    assert shipping_record_id is not None
    return int(shipping_record_id)


async def _insert_reconciliation(
    session: AsyncSession,
    *,
    status: str,
    shipping_provider_code: str,
    tracking_no: str,
    carrier_bill_item_id: int,
    shipping_record_id: int | None,
    weight_diff_kg: Decimal | None = None,
    cost_diff: Decimal | None = None,
) -> int:
    row = await session.execute(
        text(
            """
            INSERT INTO shipping_record_reconciliations (
                shipping_record_id,
                carrier_bill_item_id,
                weight_diff_kg,
                cost_diff,
                tracking_no,
                adjust_amount,
                status,
                shipping_provider_code,
                approved_reason_text,
                approved_at,
                approved_reason_code
            )
            VALUES (
                :shipping_record_id,
                :carrier_bill_item_id,
                :weight_diff_kg,
                :cost_diff,
                :tracking_no,
                NULL,
                :status,
                :shipping_provider_code,
                NULL,
                NULL,
                NULL
            )
            RETURNING id
            """
        ),
        {
            "shipping_record_id": shipping_record_id,
            "carrier_bill_item_id": carrier_bill_item_id,
            "weight_diff_kg": weight_diff_kg,
            "cost_diff": cost_diff,
            "tracking_no": tracking_no,
            "status": status,
            "shipping_provider_code": shipping_provider_code,
        },
    )
    reconciliation_id = row.scalar_one_or_none()
    assert reconciliation_id is not None
    return int(reconciliation_id)


async def _insert_history(
    session: AsyncSession,
    *,
    carrier_bill_item_id: int,
    shipping_record_id: int | None,
    shipping_provider_code: str,
    tracking_no: str,
    result_status: str,
    approved_reason_code: str,
    weight_diff_kg: Decimal | None = None,
    cost_diff: Decimal | None = None,
    adjust_amount: Decimal | None = None,
    approved_reason_text: str | None = None,
) -> int:
    row = await session.execute(
        text(
            """
            INSERT INTO shipping_bill_reconciliation_histories (
                carrier_bill_item_id,
                shipping_record_id,
                shipping_provider_code,
                tracking_no,
                result_status,
                weight_diff_kg,
                cost_diff,
                adjust_amount,
                approved_reason_text,
                approved_reason_code
            )
            VALUES (
                :carrier_bill_item_id,
                :shipping_record_id,
                :shipping_provider_code,
                :tracking_no,
                :result_status,
                :weight_diff_kg,
                :cost_diff,
                :adjust_amount,
                :approved_reason_text,
                :approved_reason_code
            )
            RETURNING id
            """
        ),
        {
            "carrier_bill_item_id": carrier_bill_item_id,
            "shipping_record_id": shipping_record_id,
            "shipping_provider_code": shipping_provider_code,
            "tracking_no": tracking_no,
            "result_status": result_status,
            "weight_diff_kg": weight_diff_kg,
            "cost_diff": cost_diff,
            "adjust_amount": adjust_amount,
            "approved_reason_text": approved_reason_text,
            "approved_reason_code": approved_reason_code,
        },
    )
    history_id = row.scalar_one_or_none()
    assert history_id is not None
    return int(history_id)


@pytest.mark.asyncio
async def test_tms_billing_reconciliations_list_contract_is_table_only(client, session: AsyncSession) -> None:
    headers = await _login_headers(client)

    shipping_provider_code = "YTO"
    tracking_no = "UT-RECON-LIST-001"

    bill_item_id = await _insert_carrier_bill_item(
        session,
        shipping_provider_code=shipping_provider_code,
        tracking_no=tracking_no,
        billing_weight_kg=Decimal("2.500"),
        freight_amount=Decimal("10.00"),
        surcharge_amount=Decimal("1.00"),
        total_amount=Decimal("11.00"),
    )
    shipping_record_id = await _insert_shipping_record(
        session,
        shipping_provider_code=shipping_provider_code,
        tracking_no=tracking_no,
        gross_weight_kg=Decimal("2.000"),
        cost_estimated=Decimal("9.50"),
    )
    await _insert_reconciliation(
        session,
        status="diff",
        shipping_provider_code=shipping_provider_code,
        tracking_no=tracking_no,
        carrier_bill_item_id=bill_item_id,
        shipping_record_id=shipping_record_id,
        weight_diff_kg=Decimal("0.500"),
        cost_diff=Decimal("1.50"),
    )

    resp = await client.get(
        "/shipping-assist/billing/reconciliations",
        params={"shipping_provider_code": shipping_provider_code, "tracking_no": tracking_no},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["ok"] is True
    assert isinstance(body["rows"], list)
    assert body["total"] >= 1

    row = body["rows"][0]
    expected_keys = {
        "reconciliation_id",
        "status",
        "shipping_provider_code",
        "tracking_no",
        "shipping_record_id",
        "carrier_bill_item_id",
        "weight_diff_kg",
        "cost_diff",
        "adjust_amount",
        "approved_reason_code",
        "approved_reason_text",
        "approved_at",
        "created_at",
    }
    assert set(row.keys()) == expected_keys

    assert row["status"] == "diff"
    assert row["shipping_provider_code"] == shipping_provider_code
    assert row["tracking_no"] == tracking_no
    assert row["shipping_record_id"] == shipping_record_id
    assert row["carrier_bill_item_id"] == bill_item_id
    assert float(row["weight_diff_kg"]) == pytest.approx(0.5)
    assert float(row["cost_diff"]) == pytest.approx(1.5)

    forbidden_keys = {
        "business_time",
        "destination_province",
        "destination_city",
        "billing_weight_kg",
        "freight_amount",
        "surcharge_amount",
        "bill_cost_real",
        "total_amount",
        "gross_weight_kg",
        "cost_estimated",
        "bill_item",
        "shipping_record",
    }
    assert forbidden_keys.isdisjoint(row.keys())


@pytest.mark.asyncio
async def test_tms_billing_reconciliation_histories_list_contract_is_table_only(client, session: AsyncSession) -> None:
    headers = await _login_headers(client)

    shipping_provider_code = "YTO"
    tracking_no = "UT-HISTORY-LIST-001"

    bill_item_id = await _insert_carrier_bill_item(
        session,
        shipping_provider_code=shipping_provider_code,
        tracking_no=tracking_no,
        billing_weight_kg=Decimal("1.000"),
        freight_amount=Decimal("8.00"),
        surcharge_amount=Decimal("1.00"),
        total_amount=Decimal("9.00"),
    )
    shipping_record_id = await _insert_shipping_record(
        session,
        shipping_provider_code=shipping_provider_code,
        tracking_no=tracking_no,
        gross_weight_kg=Decimal("1.000"),
        cost_estimated=Decimal("9.00"),
    )
    await _insert_history(
        session,
        carrier_bill_item_id=bill_item_id,
        shipping_record_id=shipping_record_id,
        shipping_provider_code=shipping_provider_code,
        tracking_no=tracking_no,
        result_status="matched",
        approved_reason_code="matched",
        weight_diff_kg=None,
        cost_diff=None,
        adjust_amount=None,
        approved_reason_text=None,
    )

    resp = await client.get(
        "/shipping-assist/billing/reconciliation-histories",
        params={"shipping_provider_code": shipping_provider_code, "tracking_no": tracking_no},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["ok"] is True
    assert isinstance(body["rows"], list)
    assert body["total"] >= 1

    row = body["rows"][0]
    expected_keys = {
        "id",
        "carrier_bill_item_id",
        "shipping_record_id",
        "shipping_provider_code",
        "tracking_no",
        "result_status",
        "approved_reason_code",
        "weight_diff_kg",
        "cost_diff",
        "adjust_amount",
        "approved_reason_text",
        "archived_at",
    }
    assert set(row.keys()) == expected_keys
    assert row["result_status"] in {"matched", "approved_bill_only", "resolved"}
    assert row["approved_reason_code"] in {"matched", "approved_bill_only", "resolved"}


@pytest.mark.asyncio
async def test_tms_billing_approve_bill_only_requires_approved_bill_only(client, session: AsyncSession) -> None:
    headers = await _login_headers(client)

    shipping_provider_code = "YTO"
    tracking_no = "UT-APPROVE-BILL-ONLY-001"

    bill_item_id = await _insert_carrier_bill_item(
        session,
        shipping_provider_code=shipping_provider_code,
        tracking_no=tracking_no,
        billing_weight_kg=Decimal("3.000"),
        freight_amount=Decimal("15.00"),
        surcharge_amount=Decimal("2.00"),
        total_amount=Decimal("17.00"),
    )
    reconciliation_id = await _insert_reconciliation(
        session,
        status="bill_only",
        shipping_provider_code=shipping_provider_code,
        tracking_no=tracking_no,
        carrier_bill_item_id=bill_item_id,
        shipping_record_id=None,
        weight_diff_kg=None,
        cost_diff=None,
    )

    bad_resp = await client.post(
        f"/shipping-assist/billing/reconciliations/{reconciliation_id}/approve",
        json={
            "approved_reason_code": "resolved",
            "adjust_amount": 0,
            "approved_reason_text": "bad-code",
        },
        headers=headers,
    )
    assert bad_resp.status_code == 422, bad_resp.text

    ok_resp = await client.post(
        f"/shipping-assist/billing/reconciliations/{reconciliation_id}/approve",
        json={
            "approved_reason_code": "approved_bill_only",
            "adjust_amount": 0,
            "approved_reason_text": "confirmed bill only",
        },
        headers=headers,
    )
    assert ok_resp.status_code == 200, ok_resp.text

    body = ok_resp.json()
    assert body["ok"] is True
    assert body["reconciliation_id"] == reconciliation_id
    assert body["history_result_status"] == "approved_bill_only"

    remaining = await session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM shipping_record_reconciliations
            WHERE id = :id
            """
        ),
        {"id": reconciliation_id},
    )
    assert int(remaining.scalar_one()) == 0

    history = await session.execute(
        text(
            """
            SELECT result_status, approved_reason_code, approved_reason_text
            FROM shipping_bill_reconciliation_histories
            WHERE carrier_bill_item_id = :carrier_bill_item_id
            """
        ),
        {"carrier_bill_item_id": bill_item_id},
    )
    history_row = history.mappings().first()
    assert history_row is not None
    assert str(history_row["result_status"]) == "approved_bill_only"
    assert str(history_row["approved_reason_code"]) == "approved_bill_only"
    assert str(history_row["approved_reason_text"]) == "confirmed bill only"


@pytest.mark.asyncio
async def test_tms_billing_approve_diff_requires_resolved(client, session: AsyncSession) -> None:
    headers = await _login_headers(client)

    shipping_provider_code = "YTO"
    tracking_no = "UT-APPROVE-DIFF-001"

    bill_item_id = await _insert_carrier_bill_item(
        session,
        shipping_provider_code=shipping_provider_code,
        tracking_no=tracking_no,
        billing_weight_kg=Decimal("2.300"),
        freight_amount=Decimal("12.00"),
        surcharge_amount=Decimal("1.00"),
        total_amount=Decimal("13.00"),
    )
    shipping_record_id = await _insert_shipping_record(
        session,
        shipping_provider_code=shipping_provider_code,
        tracking_no=tracking_no,
        gross_weight_kg=Decimal("2.000"),
        cost_estimated=Decimal("11.50"),
    )
    reconciliation_id = await _insert_reconciliation(
        session,
        status="diff",
        shipping_provider_code=shipping_provider_code,
        tracking_no=tracking_no,
        carrier_bill_item_id=bill_item_id,
        shipping_record_id=shipping_record_id,
        weight_diff_kg=Decimal("0.300"),
        cost_diff=Decimal("1.50"),
    )

    bad_resp = await client.post(
        f"/shipping-assist/billing/reconciliations/{reconciliation_id}/approve",
        json={
            "approved_reason_code": "approved_bill_only",
            "adjust_amount": 1.25,
            "approved_reason_text": "bad-code",
        },
        headers=headers,
    )
    assert bad_resp.status_code == 422, bad_resp.text

    ok_resp = await client.post(
        f"/shipping-assist/billing/reconciliations/{reconciliation_id}/approve",
        json={
            "approved_reason_code": "resolved",
            "adjust_amount": 1.25,
            "approved_reason_text": "resolved manually",
        },
        headers=headers,
    )
    assert ok_resp.status_code == 200, ok_resp.text

    body = ok_resp.json()
    assert body["ok"] is True
    assert body["reconciliation_id"] == reconciliation_id
    assert body["history_result_status"] == "resolved"

    remaining = await session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM shipping_record_reconciliations
            WHERE id = :id
            """
        ),
        {"id": reconciliation_id},
    )
    assert int(remaining.scalar_one()) == 0

    history = await session.execute(
        text(
            """
            SELECT result_status, approved_reason_code, adjust_amount, approved_reason_text
            FROM shipping_bill_reconciliation_histories
            WHERE carrier_bill_item_id = :carrier_bill_item_id
            """
        ),
        {"carrier_bill_item_id": bill_item_id},
    )
    history_row = history.mappings().first()
    assert history_row is not None
    assert str(history_row["result_status"]) == "resolved"
    assert str(history_row["approved_reason_code"]) == "resolved"
    assert float(history_row["adjust_amount"]) == pytest.approx(1.25)
    assert str(history_row["approved_reason_text"]) == "resolved manually"
