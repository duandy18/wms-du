from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text


async def _headers(client) -> dict[str, str]:
    login = await client.post(
        "/users/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _seed_finance_order_sales_line(db_session) -> str:
    platform = "PDD"
    store_code = f"FIN-ORDER-STORE-{uuid4().hex[:8]}"
    ext_order_no = f"FIN-ORDER-{uuid4().hex[:8]}"

    store_row = (
        await db_session.execute(
            text(
                """
                INSERT INTO stores (
                  platform,
                  store_code,
                  store_name,
                  active,
                  created_at,
                  updated_at
                )
                VALUES (
                  :platform,
                  :store_code,
                  :store_name,
                  TRUE,
                  now(),
                  now()
                )
                ON CONFLICT (platform, store_code)
                DO UPDATE SET
                  store_name = EXCLUDED.store_name,
                  updated_at = now()
                RETURNING id
                """
            ),
            {
                "platform": platform,
                "store_code": store_code,
                "store_name": "FIN-订单销售测试店铺",
            },
        )
    ).mappings().one()
    store_id = int(store_row["id"])

    order_row = (
        await db_session.execute(
            text(
                """
                INSERT INTO orders (
                  platform,
                  store_id,
                  store_code,
                  ext_order_no,
                  status,
                  order_amount,
                  pay_amount,
                  buyer_name,
                  buyer_phone,
                  created_at,
                  updated_at
                )
                VALUES (
                  :platform,
                  :store_id,
                  :store_code,
                  :ext_order_no,
                  'PAID',
                  49.90,
                  39.90,
                  'finance-buyer',
                  '13000000000',
                  '2026-01-03 10:00:00+00',
                  '2026-01-03 10:00:00+00'
                )
                RETURNING id
                """
            ),
            {
                "platform": platform,
                "store_id": store_id,
                "store_code": store_code,
                "ext_order_no": ext_order_no,
            },
        )
    ).mappings().one()
    order_id = int(order_row["id"])

    await db_session.execute(
        text(
            """
            INSERT INTO order_address (
              order_id,
              receiver_name,
              receiver_phone,
              province,
              city,
              district,
              detail,
              zipcode,
              created_at
            )
            VALUES (
              :order_id,
              'finance-receiver',
              '13000000000',
              '浙江省',
              '杭州市',
              '西湖区',
              '测试地址',
              '310000',
              now()
            )
            ON CONFLICT (order_id)
            DO UPDATE SET
              province = EXCLUDED.province,
              city = EXCLUDED.city,
              district = EXCLUDED.district
            """
        ),
        {"order_id": order_id},
    )

    await db_session.execute(
        text(
            """
            INSERT INTO order_items (
              order_id,
              item_id,
              qty,
              sku_id,
              title,
              price,
              discount,
              amount,
              extras,
              shipped_qty,
              returned_qty
            )
            VALUES (
              :order_id,
              1,
              2,
              'FIN-SKU-1',
              '订单销售测试商品',
              19.95,
              0,
              39.90,
              '{}'::jsonb,
              0,
              0
            )
            """
        ),
        {"order_id": order_id},
    )

    await db_session.commit()
    return ext_order_no


async def test_finance_overview_page_contract(client):
    headers = await _headers(client)

    resp = await client.get(
        "/finance/overview?from_date=2026-01-01&to_date=2026-01-07",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert set(body) == {"summary", "daily"}

    assert set(body["summary"]) == {
        "revenue",
        "purchase_cost",
        "shipping_cost",
        "gross_profit",
        "gross_margin",
        "fulfillment_ratio",
    }

    assert isinstance(body["daily"], list)
    assert body["daily"], body
    assert set(body["daily"][0]) == {
        "day",
        "revenue",
        "purchase_cost",
        "shipping_cost",
        "gross_profit",
        "gross_margin",
        "fulfillment_ratio",
    }


async def test_finance_order_sales_contract(client):
    headers = await _headers(client)

    resp = await client.get(
        "/finance/order-sales?from_date=2026-01-01&to_date=2026-01-07",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert set(body) == {
        "summary",
        "daily",
        "by_store",
        "by_item",
        "items",
        "total",
        "limit",
        "offset",
    }
    assert set(body["summary"]) == {
        "order_count",
        "line_count",
        "qty_sold",
        "revenue",
        "avg_order_value",
        "median_order_value",
    }
    assert isinstance(body["daily"], list)
    assert isinstance(body["by_store"], list)
    assert isinstance(body["by_item"], list)
    assert isinstance(body["items"], list)
    assert isinstance(body["total"], int)
    assert isinstance(body["limit"], int)
    assert isinstance(body["offset"], int)


async def test_finance_order_sales_reads_physical_sales_lines(client, session):
    ext_order_no = await _seed_finance_order_sales_line(session)
    headers = await _headers(client)

    resp = await client.get(
        "/finance/order-sales"
        f"?from_date=2026-01-01&to_date=2026-01-07&order_no={ext_order_no}",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["total"] == 1, body
    assert body["summary"]["order_count"] == 1, body
    assert body["summary"]["line_count"] == 1, body
    assert body["summary"]["qty_sold"] == 2, body
    assert Decimal(str(body["summary"]["revenue"])) == Decimal("39.90")

    item = body["items"][0]
    assert item["ext_order_no"] == ext_order_no
    assert item["order_ref"].endswith(f":{ext_order_no}")
    assert item["store_code"].startswith("FIN-ORDER-STORE-")
    assert item["store_name"] == "FIN-订单销售测试店铺"
    assert item["receiver_province"] == "浙江省"
    assert item["receiver_city"] == "杭州市"
    assert item["receiver_district"] == "西湖区"
    assert item["item_id"] == 1
    assert item["sku_id"] == "FIN-SKU-1"
    assert item["title"] == "订单销售测试商品"
    assert item["qty_sold"] == 2
    assert Decimal(str(item["line_amount"])) == Decimal("39.90")


async def test_finance_purchase_costs_contract(client):
    headers = await _headers(client)

    resp = await client.get(
        "/finance/purchase-costs?from_date=2026-01-01&to_date=2026-01-07",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert set(body) == {"summary", "daily", "by_supplier", "by_item"}
    assert set(body["summary"]) == {
        "purchase_order_count",
        "supplier_count",
        "item_count",
        "purchase_amount",
        "avg_unit_cost",
    }
    assert isinstance(body["daily"], list)
    assert isinstance(body["by_supplier"], list)
    assert isinstance(body["by_item"], list)


async def test_finance_shipping_costs_contract(client):
    headers = await _headers(client)

    resp = await client.get(
        "/finance/shipping-costs?from_date=2026-01-01&to_date=2026-01-07",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert set(body) == {"summary", "daily", "by_carrier", "by_store"}
    assert set(body["summary"]) == {
        "shipment_count",
        "estimated_shipping_cost",
        "billed_shipping_cost",
        "cost_diff",
        "adjusted_cost",
    }
    assert isinstance(body["daily"], list)
    assert isinstance(body["by_carrier"], list)
    assert isinstance(body["by_store"], list)


async def test_legacy_finance_routes_are_not_kept(client):
    headers = await _headers(client)

    legacy_paths = [
        "/finance/overview/daily",
        "/finance/store",
        "/finance/sku",
        "/finance/order-unit",
    ]

    for path in legacy_paths:
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 404, f"{path} should be retired: {resp.text}"
