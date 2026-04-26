from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text


async def _headers(client) -> dict[str, str]:
    login = await client.post(
        "/users/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _seed_finance_shipping_record(session) -> int:
    await session.execute(
        text(
            """
            INSERT INTO stores (
  id,
  platform,
  store_code,
  store_name,
  active,
  route_mode
)
VALUES (
  910001,
  'PDD',
  'FIN-STORE-1',
  'FIN-STORE-NAME-1',
  true,
  'FALLBACK'
)
            ON CONFLICT (id) DO UPDATE SET
              platform = EXCLUDED.platform,
              store_code = EXCLUDED.store_code,
              store_name = EXCLUDED.store_name,
              active = EXCLUDED.active,
              route_mode = EXCLUDED.route_mode
            """
        )
    )

    row = (
        await session.execute(
            text(
                """
                INSERT INTO shipping_records (
                  order_ref,
                  platform,
                  store_code,
                  package_no,
                  warehouse_id,
                  shipping_provider_id,
                  shipping_provider_code,
                  shipping_provider_name,
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
                  dest_city,
                  created_at
                )
                VALUES (
                  'FIN-ORDER-1',
                  'PDD',
                  'FIN-STORE-1',
                  1,
                  1,
                  1,
                  'UT-CAR-1',
                  'UT-CARRIER-1',
                  'FIN-TRACK-1',
                  1.250,
                  10.00,
                  2.34,
                  12.34,
                  10.00,
                  20.00,
                  30.00,
                  'FIN-SENDER',
                  '河北省',
                  '廊坊市',
                  '2036-02-01T10:00:00+00:00'
                )
                RETURNING id
                """
            )
        )
    ).mappings().one()

    await session.commit()
    return int(row["id"])


async def test_finance_shipping_ledger_reads_physical_lines(client, session):
    shipping_record_id = await _seed_finance_shipping_record(session)
    headers = await _headers(client)

    db_row = (
        await session.execute(
            text(
                """
                SELECT
                  shipping_record_id,
                  store_name,
                  warehouse_name,
                  shipping_provider_code,
                  shipping_provider_name,
                  freight_estimated,
                  surcharge_estimated,
                  cost_estimated
                FROM finance_shipping_cost_lines
                WHERE shipping_record_id = :shipping_record_id
                """
            ),
            {"shipping_record_id": shipping_record_id},
        )
    ).mappings().one()

    assert int(db_row["shipping_record_id"]) == shipping_record_id
    assert db_row["store_name"] == "FIN-STORE-NAME-1"
    assert db_row["warehouse_name"] == "WH-1"
    assert db_row["shipping_provider_code"] == "UT-CAR-1"
    assert db_row["shipping_provider_name"] == "UT-CARRIER-1"
    assert Decimal(str(db_row["freight_estimated"])) == Decimal("10.00")
    assert Decimal(str(db_row["surcharge_estimated"])) == Decimal("2.34")
    assert Decimal(str(db_row["cost_estimated"])) == Decimal("12.34")

    resp = await client.get(
        "/finance/shipping-costs/shipping-ledger"
        "?from_date=2036-02-01"
        "&to_date=2036-02-01"
        "&platform=PDD"
        "&store_code=FIN-STORE-1"
        "&order_keyword=FIN-ORDER-1",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert set(body) == {"rows"}
    assert len(body["rows"]) == 1

    row = body["rows"][0]
    assert set(row) == {
        "shipping_record_id",
        "platform",
        "store_code",
        "store_name",
        "order_ref",
        "package_no",
        "tracking_no",
        "warehouse_id",
        "warehouse_name",
        "shipping_provider_id",
        "shipping_provider_code",
        "shipping_provider_name",
        "shipped_time",
        "shipped_date",
        "dest_province",
        "dest_city",
        "gross_weight_kg",
        "freight_estimated",
        "surcharge_estimated",
        "cost_estimated",
    }

    assert row["shipping_record_id"] == shipping_record_id
    assert row["platform"] == "PDD"
    assert row["store_code"] == "FIN-STORE-1"
    assert row["store_name"] == "FIN-STORE-NAME-1"
    assert row["order_ref"] == "FIN-ORDER-1"
    assert row["package_no"] == 1
    assert row["tracking_no"] == "FIN-TRACK-1"
    assert row["warehouse_id"] == 1
    assert row["warehouse_name"] == "WH-1"
    assert row["shipping_provider_id"] == 1
    assert row["shipping_provider_code"] == "UT-CAR-1"
    assert row["shipping_provider_name"] == "UT-CARRIER-1"
    assert row["shipped_date"] == "2036-02-01"
    assert row["dest_province"] == "河北省"
    assert row["dest_city"] == "廊坊市"
    assert Decimal(str(row["gross_weight_kg"])) == Decimal("1.250")
    assert Decimal(str(row["freight_estimated"])) == Decimal("10.00")
    assert Decimal(str(row["surcharge_estimated"])) == Decimal("2.34")
    assert Decimal(str(row["cost_estimated"])) == Decimal("12.34")


async def test_finance_shipping_ledger_options(client, session):
    await _seed_finance_shipping_record(session)
    headers = await _headers(client)

    resp = await client.get(
        "/finance/shipping-costs/shipping-ledger/options"
        "?from_date=2036-02-01"
        "&to_date=2036-02-01"
        "&platform=PDD",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert set(body) == {"stores", "warehouses", "providers"}

    assert body["stores"] == [
        {
            "platform": "PDD",
            "store_code": "FIN-STORE-1",
            "store_name": "FIN-STORE-NAME-1",
        }
    ]

    assert body["warehouses"] == [
        {
            "warehouse_id": 1,
            "warehouse_name": "WH-1",
        }
    ]

    assert body["providers"] == [
        {
            "shipping_provider_id": 1,
            "shipping_provider_code": "UT-CAR-1",
            "shipping_provider_name": "UT-CARRIER-1",
        }
    ]
