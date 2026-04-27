from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _insert_pdd_order_with_items(session) -> int:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO stores(platform, store_code, store_name, active, created_at, updated_at)
                VALUES ('PDD', 'PDD-BRIDGE-STORE', 'PDD Bridge Store', true, now(), now())
                ON CONFLICT (platform, store_code) DO UPDATE
                  SET store_name = EXCLUDED.store_name,
                      active = true,
                      updated_at = now()
                RETURNING id
                """
            )
        )
    ).mappings().first()
    assert row and row.get("id") is not None
    store_id = int(row["id"])

    order_row = (
        await session.execute(
            text(
                """
                INSERT INTO pdd_orders(
                  store_id,
                  order_sn,
                  order_status,
                  receiver_name,
                  receiver_phone,
                  receiver_province,
                  receiver_city,
                  receiver_district,
                  receiver_address,
                  buyer_memo,
                  remark,
                  confirm_at,
                  goods_amount,
                  pay_amount,
                  raw_summary_payload,
                  raw_detail_payload,
                  pulled_at,
                  last_synced_at,
                  created_at,
                  updated_at
                )
                VALUES (
                  :store_id,
                  :order_sn,
                  '1',
                  '张三',
                  '13800138000',
                  '上海市',
                  '上海市',
                  '浦东新区',
                  '科苑路 88 号',
                  '请尽快发货',
                  '桥接测试',
                  now(),
                  41.57,
                  41.57,
                  '{"source":"unit-summary"}'::jsonb,
                  '{"source":"unit-detail"}'::jsonb,
                  now(),
                  now(),
                  now(),
                  now()
                )
                ON CONFLICT (store_id, order_sn) DO UPDATE
                  SET updated_at = now()
                RETURNING id
                """
            ),
            {
                "store_id": store_id,
                "order_sn": "PDD-BRIDGE-ORDER-001",
            },
        )
    ).mappings().first()
    assert order_row and order_row.get("id") is not None
    pdd_order_id = int(order_row["id"])

    await session.execute(
        text("DELETE FROM pdd_order_items WHERE pdd_order_id = :pdd_order_id"),
        {"pdd_order_id": pdd_order_id},
    )

    await session.execute(
        text(
            """
            INSERT INTO pdd_order_items(
              pdd_order_id,
              order_sn,
              platform_goods_id,
              platform_sku_id,
              outer_id,
              goods_name,
              goods_count,
              goods_price,
              raw_item_payload,
              created_at,
              updated_at
            )
            VALUES
              (
                :pdd_order_id,
                'PDD-BRIDGE-ORDER-001',
                'G-001',
                'SKU-001',
                'OUTER-FSKU-001',
                '拼多多桥接商品A',
                2,
                12.99,
                '{"source":"unit-item-a"}'::jsonb,
                now(),
                now()
              ),
              (
                :pdd_order_id,
                'PDD-BRIDGE-ORDER-001',
                'G-002',
                'SKU-002',
                NULL,
                '拼多多桥接商品B',
                1,
                15.59,
                '{"source":"unit-item-b"}'::jsonb,
                now(),
                now()
              )
            """
        ),
        {"pdd_order_id": pdd_order_id},
    )

    await session.commit()
    return pdd_order_id


async def test_post_pdd_order_fact_bridge_writes_platform_order_lines(client, session):
    pdd_order_id = await _insert_pdd_order_with_items(session)

    resp = await client.post(f"/oms/pdd/orders/{pdd_order_id}/facts/bridge")
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["platform"] == "PDD"
    assert data["store_code"] == "PDD-BRIDGE-STORE"
    assert data["pdd_order_id"] == pdd_order_id
    assert data["ext_order_no"] == "PDD-BRIDGE-ORDER-001"
    assert data["lines_count"] == 2
    assert data["facts_written"] == 2

    rows = (
        await session.execute(
            text(
                """
                SELECT
                  line_no,
                  line_key,
                  locator_kind,
                  locator_value,
                  filled_code,
                  qty,
                  title,
                  spec,
                  extras
                FROM platform_order_lines
                WHERE platform = 'PDD'
                  AND store_code = 'PDD-BRIDGE-STORE'
                  AND ext_order_no = 'PDD-BRIDGE-ORDER-001'
                ORDER BY line_no ASC
                """
            )
        )
    ).mappings().all()

    assert len(rows) == 2

    first = rows[0]
    assert first["line_no"] == 1
    assert first["line_key"] == "PSKU:OUTER-FSKU-001"
    assert first["locator_kind"] == "FILLED_CODE"
    assert first["locator_value"] == "OUTER-FSKU-001"
    assert first["filled_code"] == "OUTER-FSKU-001"
    assert first["qty"] == 2
    assert first["title"] == "拼多多桥接商品A"
    assert first["spec"] == "goods_id:G-001 / sku_id:SKU-001"
    assert first["extras"]["source"] == "pdd_order_items"
    assert first["extras"]["platform_goods_id"] == "G-001"
    assert first["extras"]["platform_sku_id"] == "SKU-001"
    assert first["extras"]["outer_id"] == "OUTER-FSKU-001"
    assert Decimal(str(first["extras"]["goods_price"])) == Decimal("12.99")

    second = rows[1]
    assert second["line_no"] == 2
    assert second["line_key"] == "NO_PSKU:2"
    assert second["locator_kind"] == "LINE_NO"
    assert second["locator_value"] == "2"
    assert second["filled_code"] is None
    assert second["qty"] == 1
    assert second["title"] == "拼多多桥接商品B"
    assert second["spec"] == "goods_id:G-002 / sku_id:SKU-002"


async def test_post_pdd_order_fact_bridge_is_idempotent(client, session):
    pdd_order_id = await _insert_pdd_order_with_items(session)

    r1 = await client.post(f"/oms/pdd/orders/{pdd_order_id}/facts/bridge")
    assert r1.status_code == 200, r1.text

    r2 = await client.post(f"/oms/pdd/orders/{pdd_order_id}/facts/bridge")
    assert r2.status_code == 200, r2.text

    count_row = (
        await session.execute(
            text(
                """
                SELECT count(*) AS n
                FROM platform_order_lines
                WHERE platform = 'PDD'
                  AND store_code = 'PDD-BRIDGE-STORE'
                  AND ext_order_no = 'PDD-BRIDGE-ORDER-001'
                """
            )
        )
    ).mappings().one()

    assert int(count_row["n"]) == 2


async def test_post_pdd_order_fact_bridge_returns_400_when_missing(client):
    resp = await client.post("/oms/pdd/orders/999999999/facts/bridge")
    assert resp.status_code == 400, resp.text
    assert "pdd order not found" in resp.text
