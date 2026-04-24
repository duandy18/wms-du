from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.oms.platforms.models.jd_order import JdOrder, JdOrderItem
from app.oms.platforms.jd import service_ledger as jd_ledger_module


def _build_order() -> JdOrder:
    now = datetime(2026, 3, 30, 10, 0, 0, tzinfo=timezone.utc)
    order = JdOrder(
        id=1,
        store_id=919,
        order_id="JD202603300001",
        vender_id="VENDER-919",
        order_type="SOP",
        order_state="WAIT_SELLER_STOCK_OUT",
        buyer_pin="buyer_pin_demo_001",
        consignee_name="张三",
        consignee_mobile="13800138000",
        consignee_phone=None,
        consignee_province="上海市",
        consignee_city="上海市",
        consignee_county="浦东新区",
        consignee_town="张江镇",
        consignee_address="科苑路 88 号 1 栋 502",
        order_remark="请尽快发货",
        seller_remark="JD 测试订单 1",
        order_total_price=Decimal("128.50"),
        order_seller_price=Decimal("120.00"),
        freight_price=Decimal("8.50"),
        payment_confirm="true",
        order_start_time=now,
        order_end_time=None,
        modified=now,
        raw_summary_payload={"order_id": "JD202603300001"},
        raw_detail_payload={"order_id": "JD202603300001"},
        pulled_at=now,
        last_synced_at=now,
        created_at=now,
        updated_at=now,
    )
    order.items = [
        JdOrderItem(
            id=11,
            jd_order_id=1,
            order_id="JD202603300001",
            sku_id="SKU-JD-1001",
            outer_sku_id="OUTER-SKU-001",
            ware_id="WARE-001",
            item_name="京东测试商品A",
            item_total=2,
            item_price=Decimal("39.90"),
            sku_name="颜色:黑;尺码:M",
            gift_point=0,
            raw_item_payload={"sku_id": "SKU-JD-1001"},
        )
    ]
    return order


def test_serialize_row_formats_fields():
    row = _build_order()

    data = jd_ledger_module._serialize_row(row)

    assert data.id == 1
    assert data.store_id == 919
    assert data.order_id == "JD202603300001"
    assert data.order_state == "WAIT_SELLER_STOCK_OUT"
    assert data.order_type == "SOP"
    assert data.order_total_price == "128.50"
    assert data.order_seller_price == "120.00"
    assert data.order_start_time == "2026-03-30T10:00:00+00:00"
    assert data.modified == "2026-03-30T10:00:00+00:00"
    assert data.pulled_at == "2026-03-30T10:00:00+00:00"
    assert data.last_synced_at == "2026-03-30T10:00:00+00:00"


def test_serialize_item_formats_fields():
    row = _build_order()
    item = row.items[0]

    data = jd_ledger_module._serialize_item(item)

    assert data.id == 11
    assert data.jd_order_id == 1
    assert data.order_id == "JD202603300001"
    assert data.sku_id == "SKU-JD-1001"
    assert data.outer_sku_id == "OUTER-SKU-001"
    assert data.ware_id == "WARE-001"
    assert data.item_name == "京东测试商品A"
    assert data.item_total == 2
    assert data.item_price == "39.90"
    assert data.sku_name == "颜色:黑;尺码:M"
    assert data.gift_point == 0


def test_serialize_detail_formats_header_and_items():
    row = _build_order()

    data = jd_ledger_module._serialize_detail(row)

    assert data.id == 1
    assert data.store_id == 919
    assert data.order_id == "JD202603300001"
    assert data.vender_id == "VENDER-919"
    assert data.order_type == "SOP"
    assert data.order_state == "WAIT_SELLER_STOCK_OUT"
    assert data.buyer_pin == "buyer_pin_demo_001"
    assert data.consignee_name == "张三"
    assert data.consignee_mobile == "13800138000"
    assert data.consignee_province == "上海市"
    assert data.consignee_city == "上海市"
    assert data.consignee_county == "浦东新区"
    assert data.consignee_town == "张江镇"
    assert data.consignee_address == "科苑路 88 号 1 栋 502"
    assert data.order_remark == "请尽快发货"
    assert data.seller_remark == "JD 测试订单 1"
    assert data.order_total_price == "128.50"
    assert data.order_seller_price == "120.00"
    assert data.freight_price == "8.50"
    assert data.payment_confirm == "true"
    assert data.order_start_time == "2026-03-30T10:00:00+00:00"
    assert data.modified == "2026-03-30T10:00:00+00:00"
    assert isinstance(data.items, list)
    assert len(data.items) == 1
    assert data.items[0].sku_id == "SKU-JD-1001"


@pytest.mark.asyncio
async def test_get_jd_order_ledger_detail_returns_none_when_missing(monkeypatch):
    async def _fake_get_jd_order_with_items(session, *, jd_order_id: int):
        assert jd_order_id == 999
        return None

    monkeypatch.setattr(
        jd_ledger_module,
        "get_jd_order_with_items",
        _fake_get_jd_order_with_items,
    )

    result = await jd_ledger_module.get_jd_order_ledger_detail(
        session=None,
        jd_order_id=999,
    )

    assert result is None
