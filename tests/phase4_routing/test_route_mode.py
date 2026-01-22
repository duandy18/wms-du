# tests/services/test_order_route_mode_phase4.py

"""
Phase 4.x routing worldview tests

Candidate set:
  - store_province_routes (candidate-set cutter)
  - store_warehouse (capability declaration + ordering preference)

Fact check:
  - StockAvailabilityService / WarehouseRouter whole-order checks

Contract:
  - address.province is required
  - missing province => FULFILLMENT_BLOCKED (no implicit fallback selection)
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.services.order_service import OrderService
from app.services.stock_availability_service import StockAvailabilityService

from tests.helpers.phase4_routing_helpers import (
    UTC,
    bind_store_warehouses,
    ensure_store,
    ensure_store_province_route,
    ensure_two_warehouses,
)

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_route_mode_fallback_uses_backup(db_session_like_pg, monkeypatch):
    """
    RouteMode 在新世界观里的意义：
    - STRICT_TOP：省级候选集为空则不扩大（直接 NO_PROVINCE_ROUTE_MATCH）
    - FALLBACK：省级候选集为空则扩大到 store_warehouse bindings（再做事实裁决）
    但不代表“自动帮你选仓发货”，是否可履约仍由事实裁决决定。

    本用例：省码命中 top_wh，但 top_wh 不足 → BLOCKED（INSUFFICIENT_QTY）。
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S-FB"

    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    top_wh, backup_wh = await ensure_two_warehouses(session)
    store_id = await bind_store_warehouses(
        session,
        platform=platform,
        shop_id=shop_id,
        top_warehouse_id=top_wh,
        backup_warehouse_id=backup_wh,
        route_mode="FALLBACK",
    )

    province = "P-FB"
    await ensure_store_province_route(session, store_id=store_id, province=province, warehouse_id=top_wh)

    stock_map = {
        (top_wh, 1): 2,
        (backup_wh, 1): 10,
    }

    async def fake_get_available(self, *_, **kwargs):
        warehouse_id = kwargs.get("warehouse_id")
        item_id = kwargs.get("item_id")
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(StockAvailabilityService, "get_available_for_item", fake_get_available)

    res = await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no="FB-1",
        occurred_at=datetime.now(UTC),
        buyer_name="A",
        buyer_phone="111",
        order_amount=50,
        pay_amount=50,
        items=[
            {
                "item_id": 1,
                "sku_id": "SKU-1",
                "title": "FB 商品",
                "qty": 5,
                "price": 10,
                "discount": 0,
                "amount": 50,
            }
        ],
        address={"province": province, "receiver_name": "A", "receiver_phone": "111"},
        extras={},
        trace_id="TRACE-FB-1",
    )

    assert res["status"] == "FULFILLMENT_BLOCKED"
    assert isinstance(res.get("route"), dict)
    assert res["route"].get("reason") == "INSUFFICIENT_QTY"

    oid = res["id"]
    row = await session.execute(
        text("SELECT warehouse_id, fulfillment_status FROM orders WHERE id=:id"),
        {"id": oid},
    )
    whid, fstat = row.first()
    assert whid in (None, 0)
    assert str(fstat) == "FULFILLMENT_BLOCKED"


@pytest.mark.asyncio
async def test_route_mode_strict_top_does_not_fallback(db_session_like_pg, monkeypatch):
    """
    STRICT_TOP：候选集来自省级路由命中集合（不扩大）。
    本用例仍然省码命中 top_wh，但 top_wh 不足 → BLOCKED（INSUFFICIENT_QTY）。
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S-STRICT"

    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    top_wh, backup_wh = await ensure_two_warehouses(session)
    store_id = await bind_store_warehouses(
        session,
        platform=platform,
        shop_id=shop_id,
        top_warehouse_id=top_wh,
        backup_warehouse_id=backup_wh,
        route_mode="STRICT_TOP",
    )

    province = "P-STRICT"
    await ensure_store_province_route(session, store_id=store_id, province=province, warehouse_id=top_wh)

    stock_map = {
        (top_wh, 1): 2,
        (backup_wh, 1): 10,
    }

    async def fake_get_available(self, *_, **kwargs):
        warehouse_id = kwargs.get("warehouse_id")
        item_id = kwargs.get("item_id")
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(StockAvailabilityService, "get_available_for_item", fake_get_available)

    res = await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no="ST-1",
        occurred_at=datetime.now(UTC),
        buyer_name="B",
        buyer_phone="222",
        order_amount=50,
        pay_amount=50,
        items=[
            {
                "item_id": 1,
                "sku_id": "SKU-1",
                "title": "STRICT 商品",
                "qty": 5,
                "price": 10,
                "discount": 0,
                "amount": 50,
            }
        ],
        address={"province": province, "receiver_name": "B", "receiver_phone": "222"},
        extras={},
        trace_id="TRACE-ST-1",
    )

    assert res["status"] == "FULFILLMENT_BLOCKED"
    assert isinstance(res.get("route"), dict)
    assert res["route"].get("reason") == "INSUFFICIENT_QTY"

    oid = res["id"]
    row = await session.execute(
        text("SELECT warehouse_id, fulfillment_status FROM orders WHERE id=:id"),
        {"id": oid},
    )
    whid, fstat = row.first()
    assert whid in (None, 0)
    assert str(fstat) == "FULFILLMENT_BLOCKED"
