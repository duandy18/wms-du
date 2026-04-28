from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text


pytestmark = pytest.mark.asyncio


async def _clear_rows(session) -> None:
    await session.execute(text("DELETE FROM merchant_code_fsku_bindings"))
    await session.execute(text("DELETE FROM oms_pdd_order_mirror_lines"))
    await session.execute(text("DELETE FROM oms_taobao_order_mirror_lines"))
    await session.execute(text("DELETE FROM oms_jd_order_mirror_lines"))
    await session.execute(text("DELETE FROM oms_pdd_order_mirrors"))
    await session.execute(text("DELETE FROM oms_taobao_order_mirrors"))
    await session.execute(text("DELETE FROM oms_jd_order_mirrors"))
    await session.commit()


async def _pick_any_item_id(session) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT id
                FROM items
                ORDER BY id ASC
                LIMIT 1
                """
            )
        )
    ).first()
    assert row is not None, "expected at least one baseline item"
    return int(row[0])


async def _ensure_store(session, *, platform: str, store_code: str) -> int:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO stores (
                  platform,
                  store_code,
                  store_name,
                  active
                )
                VALUES (
                  upper(:platform),
                  :store_code,
                  :store_name,
                  true
                )
                ON CONFLICT (platform, store_code) DO UPDATE
                SET
                  store_name = EXCLUDED.store_name,
                  active = EXCLUDED.active
                RETURNING id
                """
            ),
            {
                "platform": platform,
                "store_code": store_code,
                "store_name": f"{platform}-{store_code}",
            },
        )
    ).mappings().one()
    await session.commit()
    return int(row["id"])


async def _create_published_fsku_with_component(
    session,
    *,
    item_id: int,
    code: str,
    name: str,
    component_qty: int = 1,
) -> int:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO fskus (
                  code,
                  name,
                  shape,
                  status,
                  published_at,
                  created_at,
                  updated_at
                )
                VALUES (
                  :code,
                  :name,
                  'single',
                  'published',
                  now(),
                  now(),
                  now()
                )
                RETURNING id
                """
            ),
            {"code": code, "name": name},
        )
    ).mappings().one()

    fsku_id = int(row["id"])

    await session.execute(
        text(
            """
            INSERT INTO fsku_components (
              fsku_id,
              item_id,
              qty,
              role,
              created_at,
              updated_at
            )
            VALUES (
              :fsku_id,
              :item_id,
              :qty,
              'primary',
              now(),
              now()
            )
            """
        ),
        {
            "fsku_id": fsku_id,
            "item_id": int(item_id),
            "qty": int(component_qty),
        },
    )

    await session.commit()
    return fsku_id


async def _create_pdd_mirror(
    session,
    *,
    store_id: int,
    store_code: str,
    order_no: str,
    merchant_code: str,
) -> int:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO oms_pdd_order_mirrors (
                  collector_order_id,
                  collector_store_id,
                  collector_store_code,
                  collector_store_name,
                  wms_store_id,
                  platform_order_no,
                  platform_status,
                  receiver_json,
                  amounts_json
                )
                VALUES (
                  :collector_order_id,
                  :collector_store_id,
                  :store_code,
                  'PDD 履约转化测试店铺',
                  :store_id,
                  :order_no,
                  'WAIT_SELLER_SEND_GOODS',
                  jsonb_build_object(
                    'name', '张三',
                    'phone', '13800000000',
                    'province', '浙江省',
                    'city', '杭州市',
                    'district', '西湖区',
                    'address', '文三路 1 号'
                  ),
                  jsonb_build_object('pay_amount', '86.00')
                )
                RETURNING id
                """
            ),
            {
                "collector_order_id": abs(hash(order_no)) % 1000000000,
                "collector_store_id": 880001,
                "store_code": store_code,
                "store_id": int(store_id),
                "order_no": order_no,
            },
        )
    ).mappings().one()

    mirror_id = int(row["id"])

    await session.execute(
        text(
            """
            INSERT INTO oms_pdd_order_mirror_lines (
              mirror_id,
              collector_line_id,
              collector_order_id,
              platform_order_no,
              merchant_sku,
              platform_item_id,
              platform_sku_id,
              title,
              quantity,
              unit_price,
              line_amount
            )
            VALUES (
              :mirror_id,
              :collector_line_id,
              880001,
              :order_no,
              :merchant_code,
              'PDD-ITEM-1',
              'PDD-SKU-1',
              'PDD 履约转化测试商品',
              2,
              43.00,
              86.00
            )
            """
        ),
        {
            "mirror_id": mirror_id,
            "collector_line_id": mirror_id + 1000,
            "order_no": order_no,
            "merchant_code": merchant_code,
        },
    )

    await session.commit()
    return mirror_id


async def test_pdd_fulfillment_order_conversion_creates_oms_order(
    client,
    session,
    monkeypatch,
) -> None:
    await _clear_rows(session)

    suffix = uuid4().hex[:8]
    store_code = f"PDD-FULFILL-{suffix}"
    merchant_code = f"PDD-FSKU-FULFILL-{suffix}"
    order_no = f"PDD-FULFILL-ORDER-{suffix}"

    monkeypatch.setenv("TEST_STORE_ID", store_code)

    item_id = await _pick_any_item_id(session)
    store_id = await _ensure_store(session, platform="pdd", store_code=store_code)
    fsku_id = await _create_published_fsku_with_component(
        session,
        item_id=item_id,
        code=f"FSKU-FULFILL-{suffix}",
        name="履约转化 FSKU",
        component_qty=1,
    )
    mirror_id = await _create_pdd_mirror(
        session,
        store_id=store_id,
        store_code=store_code,
        order_no=order_no,
        merchant_code=merchant_code,
    )

    await session.execute(
        text(
            """
            INSERT INTO merchant_code_fsku_bindings (
              platform,
              store_code,
              merchant_code,
              fsku_id,
              reason,
              created_at,
              updated_at
            )
            VALUES (
              'PDD',
              :store_code,
              :merchant_code,
              :fsku_id,
              'fulfillment conversion test',
              now(),
              now()
            )
            """
        ),
        {
            "store_code": store_code,
            "merchant_code": merchant_code,
            "fsku_id": fsku_id,
        },
    )
    await session.commit()

    resp = await client.post(
        "/oms/pdd/fulfillment-order-conversion/convert",
        json={"mirror_id": mirror_id},
    )
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["ok"] is True
    assert data["platform"] == "PDD"
    assert data["mirror_id"] == mirror_id
    assert data["store_id"] == store_id
    assert data["store_code"] == store_code
    assert data["ext_order_no"] == order_no
    assert data["lines_count"] == 1
    assert data["item_lines_count"] == 1

    order_id = int(data["order_id"])
    assert order_id > 0

    head = (
        await session.execute(
            text(
                """
                SELECT platform, store_code, ext_order_no, store_id, buyer_name, buyer_phone
                FROM orders
                WHERE id = :order_id
                LIMIT 1
                """
            ),
            {"order_id": order_id},
        )
    ).mappings().one()

    assert head["platform"] == "PDD"
    assert head["store_code"] == store_code
    assert head["ext_order_no"] == order_no
    assert int(head["store_id"]) == store_id
    assert head["buyer_name"] == "张三"

    line = (
        await session.execute(
            text(
                """
                SELECT item_id, req_qty
                FROM order_lines
                WHERE order_id = :order_id
                ORDER BY id ASC
                LIMIT 1
                """
            ),
            {"order_id": order_id},
        )
    ).mappings().one()

    assert int(line["item_id"]) == item_id
    assert int(line["req_qty"]) == 2

    second = await client.post(
        "/oms/pdd/fulfillment-order-conversion/convert",
        json={"mirror_id": mirror_id},
    )
    assert second.status_code == 200, second.text
    assert int(second.json()["order_id"]) == order_id


async def test_pdd_fulfillment_order_conversion_rejects_unbound_merchant_code(
    client,
    session,
    monkeypatch,
) -> None:
    await _clear_rows(session)

    suffix = uuid4().hex[:8]
    store_code = f"PDD-FULFILL-UNBOUND-{suffix}"
    order_no = f"PDD-FULFILL-UNBOUND-ORDER-{suffix}"

    monkeypatch.setenv("TEST_STORE_ID", store_code)

    store_id = await _ensure_store(session, platform="pdd", store_code=store_code)
    mirror_id = await _create_pdd_mirror(
        session,
        store_id=store_id,
        store_code=store_code,
        order_no=order_no,
        merchant_code=f"PDD-UNBOUND-{suffix}",
    )

    resp = await client.post(
        "/oms/pdd/fulfillment-order-conversion/convert",
        json={"mirror_id": mirror_id},
    )

    assert resp.status_code == 422, resp.text
    assert "未绑定 FSKU" in resp.text


async def test_fulfillment_order_conversion_routes_are_platform_separated(
    client,
    session,
) -> None:
    await _clear_rows(session)

    resp = await client.post(
        "/oms/taobao/fulfillment-order-conversion/convert",
        json={"mirror_id": 999999},
    )

    assert resp.status_code == 404, resp.text
    assert "taobao platform order mirror not found" in resp.text
