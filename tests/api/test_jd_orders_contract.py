from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.user.deps.auth import get_current_user
from app.main import app
from app.models.jd_order import JdOrder, JdOrderItem
import app.oms.platforms.jd.router_orders as jd_router_orders


class _TestUser:
    id: int = 999
    username: str = "test-user"
    is_active: bool = True


pytestmark = pytest.mark.asyncio


def _store_row_sql(store_id: int) -> str:
    return f"""
    INSERT INTO stores (
        id, platform, shop_id, store_code, name, active
    ) VALUES (
        {store_id},
        'jd',
        'shop-{store_id}',
        'SC{store_id}',
        'store-{store_id}',
        true
    )
    ON CONFLICT (id) DO NOTHING
    """


async def _clear_jd_orders(session) -> None:
    await session.execute(text("DELETE FROM jd_order_items"))
    await session.execute(text("DELETE FROM jd_orders"))
    await session.commit()


@pytest.mark.asyncio
async def test_get_jd_orders_returns_list_rows(client, session, monkeypatch):
    await _clear_jd_orders(session)
    await session.execute(text(_store_row_sql(701)))

    now = datetime.now(timezone.utc)
    session.add(
        JdOrder(
            store_id=701,
            order_id="JD-ORDER-701",
            vender_id="VENDER-701",
            order_type="SOP",
            order_state="WAIT_SELLER_STOCK_OUT",
            buyer_pin="buyer-701",
            consignee_name="张三",
            consignee_mobile="13800138000",
            consignee_province="上海市",
            consignee_city="上海市",
            consignee_county="浦东新区",
            consignee_town="张江镇",
            consignee_address="测试路 1 号",
            order_remark="请尽快发货",
            seller_remark="测试备注",
            order_total_price=Decimal("128.50"),
            order_seller_price=Decimal("120.00"),
            freight_price=Decimal("8.50"),
            payment_confirm="true",
            order_start_time=now,
            modified=now,
            raw_summary_payload={"order_id": "JD-ORDER-701"},
            raw_detail_payload={"order_id": "JD-ORDER-701"},
        )
    )
    await session.commit()

    app.dependency_overrides[get_current_user] = lambda: _TestUser()
    monkeypatch.setattr(jd_router_orders, "check_perm", lambda db, current_user, required: None)

    try:
        resp = await client.get("/oms/jd/orders")
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["ok"] is True
        data = body["data"]

        assert isinstance(data, list)
        assert len(data) >= 1
        row = data[0]
        assert row["store_id"] == 701
        assert row["order_id"] == "JD-ORDER-701"
        assert row["order_state"] == "WAIT_SELLER_STOCK_OUT"
        assert row["order_type"] == "SOP"
        assert row["order_total_price"] == "128.50"
        assert row["order_seller_price"] == "120.00"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_jd_order_detail_returns_header_and_items(client, session, monkeypatch):
    await _clear_jd_orders(session)
    await session.execute(text(_store_row_sql(702)))

    now = datetime.now(timezone.utc)
    order = JdOrder(
        store_id=702,
        order_id="JD-ORDER-702",
        vender_id="VENDER-702",
        order_type="SOP",
        order_state="FINISHED_L",
        buyer_pin="buyer-702",
        consignee_name="李四",
        consignee_mobile="13900139000",
        consignee_phone="021-88886666",
        consignee_province="浙江省",
        consignee_city="杭州市",
        consignee_county="西湖区",
        consignee_town="转塘街道",
        consignee_address="云栖小镇 18 号",
        order_remark="周末送货",
        seller_remark="JD 测试订单 2",
        order_total_price=Decimal("256.00"),
        order_seller_price=Decimal("246.00"),
        freight_price=Decimal("10.00"),
        payment_confirm="true",
        order_start_time=now,
        order_end_time=now,
        modified=now,
        raw_summary_payload={"order_id": "JD-ORDER-702"},
        raw_detail_payload={"order_id": "JD-ORDER-702", "items": []},
    )
    session.add(order)
    await session.flush()

    session.add(
        JdOrderItem(
            jd_order_id=order.id,
            order_id="JD-ORDER-702",
            sku_id="SKU-JD-702",
            outer_sku_id="OUTER-SKU-702",
            ware_id="WARE-702",
            item_name="京东测试商品C",
            item_total=4,
            item_price=Decimal("61.50"),
            sku_name="颜色:白;容量:1L",
            gift_point=0,
            raw_item_payload={"sku_id": "SKU-JD-702"},
        )
    )
    await session.commit()

    app.dependency_overrides[get_current_user] = lambda: _TestUser()
    monkeypatch.setattr(jd_router_orders, "check_perm", lambda db, current_user, required: None)

    try:
        resp = await client.get(f"/oms/jd/orders/{order.id}")
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["ok"] is True
        data = body["data"]

        assert data["id"] == order.id
        assert data["store_id"] == 702
        assert data["order_id"] == "JD-ORDER-702"
        assert data["order_state"] == "FINISHED_L"
        assert data["consignee_name"] == "李四"
        assert data["consignee_mobile"] == "13900139000"
        assert data["order_total_price"] == "256.00"
        assert data["order_seller_price"] == "246.00"
        assert isinstance(data["items"], list)
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["sku_id"] == "SKU-JD-702"
        assert item["outer_sku_id"] == "OUTER-SKU-702"
        assert item["ware_id"] == "WARE-702"
        assert item["item_name"] == "京东测试商品C"
        assert item["item_total"] == 4
        assert item["item_price"] == "61.50"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_jd_order_detail_returns_404_when_missing(client, session, monkeypatch):
    await _clear_jd_orders(session)

    app.dependency_overrides[get_current_user] = lambda: _TestUser()
    monkeypatch.setattr(jd_router_orders, "check_perm", lambda db, current_user, required: None)

    try:
        resp = await client.get("/oms/jd/orders/999999")
        assert resp.status_code == 404, resp.text
        assert "jd order not found" in resp.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)
