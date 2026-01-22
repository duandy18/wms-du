# tests/services/test_order_service_phase4_routing.py

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

import app.services.order_ingest_service as order_ingest_service
from tests.helpers.phase4_routing_helpers import (
    UTC,
    bind_store_warehouses,
    ensure_store_province_route,
    ensure_two_warehouses,
)

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_ingest_routes_to_top_warehouse_when_in_stock(db_session_like_pg, monkeypatch):
    """
    Route C：省码命中候选仓（store_province_routes）且库存足够时，应写入 orders.warehouse_id（READY_TO_FULFILL）。
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S1"

    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    async def _noop_reserve_flow(*_, **__):
        return None

    monkeypatch.setattr(order_ingest_service, "reserve_flow", _noop_reserve_flow)

    top_wid, backup_wid = await ensure_two_warehouses(session)
    store_id = await bind_store_warehouses(
        session,
        platform=platform,
        shop_id=shop_id,
        top_warehouse_id=top_wid,
        backup_warehouse_id=backup_wid,
    )

    province = "P-SVC-TOP"
    await ensure_store_province_route(session, store_id=store_id, province=province, warehouse_id=top_wid)

    stock_map = {
        (top_wid, 1): 10,
        (backup_wid, 1): 10,
    }

    async def fake_get_available(self, *_, **kwargs):
        warehouse_id = kwargs.get("warehouse_id")
        item_id = kwargs.get("item_id")
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(StockAvailabilityService, "get_available_for_item", fake_get_available)

    ext_order_no = "E-top-1"
    occurred_at = datetime.now(UTC)

    result = await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        occurred_at=occurred_at,
        buyer_name="张三",
        buyer_phone="13800000000",
        order_amount=50,
        pay_amount=50,
        items=[
            {
                "item_id": 1,
                "sku_id": "SKU-1",
                "title": "主仓测试商品",
                "qty": 5,
                "price": 10,
                "discount": 0,
                "amount": 50,
            }
        ],
        address={"province": province, "receiver_name": "张三", "receiver_phone": "13800000000"},
        extras={},
        trace_id="TRACE-PH4-001",
    )

    assert result["status"] == "OK"
    order_id = result["id"]

    row = await session.execute(
        text("SELECT warehouse_id, fulfillment_status FROM orders WHERE id = :id"),
        {"id": order_id},
    )
    warehouse_id, fstat = row.first()
    assert int(warehouse_id) == int(top_wid)
    assert str(fstat) in ("READY_TO_FULFILL", "FULFILLMENT_OVERRIDDEN", "RESERVED")


@pytest.mark.asyncio
async def test_ingest_routes_to_backup_when_top_insufficient(db_session_like_pg, monkeypatch):
    """
    旧 Phase4 语义：主仓不足应 fallback 到备仓。

    Route C 新事实：不兜底、不选仓；候选仓（省级路由命中）不足 → FULFILLMENT_BLOCKED（INSUFFICIENT_QTY）。
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S1"

    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    top_wid, backup_wid = await ensure_two_warehouses(session)
    store_id = await bind_store_warehouses(
        session,
        platform=platform,
        shop_id=shop_id,
        top_warehouse_id=top_wid,
        backup_warehouse_id=backup_wid,
    )

    province = "P-SVC-INS1"
    await ensure_store_province_route(session, store_id=store_id, province=province, warehouse_id=top_wid)

    stock_map = {
        (top_wid, 1): 2,  # 候选仓不够
        (backup_wid, 1): 10,  # 备仓有货（不会被选，因为候选集裁剪只剩 top_wid）
    }

    async def fake_get_available(self, *_, **kwargs):
        warehouse_id = kwargs.get("warehouse_id")
        item_id = kwargs.get("item_id")
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(StockAvailabilityService, "get_available_for_item", fake_get_available)

    ext_order_no = "E-backup-1"
    occurred_at = datetime.now(UTC)

    result = await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        occurred_at=occurred_at,
        buyer_name="李四",
        buyer_phone="13900000000",
        order_amount=50,
        pay_amount=50,
        items=[
            {
                "item_id": 1,
                "sku_id": "SKU-1",
                "title": "备仓测试商品",
                "qty": 5,
                "price": 10,
                "discount": 0,
                "amount": 50,
            }
        ],
        address={"province": province, "receiver_name": "李四", "receiver_phone": "13900000000"},
        extras={},
        trace_id="TRACE-PH4-002",
    )

    assert result["status"] == "FULFILLMENT_BLOCKED"
    assert isinstance(result.get("route"), dict)
    assert result["route"].get("reason") == "INSUFFICIENT_QTY"

    order_id = result["id"]
    row = await session.execute(
        text("SELECT warehouse_id, fulfillment_status FROM orders WHERE id = :id"),
        {"id": order_id},
    )
    whid, fstat = row.first()
    assert whid in (None, 0)
    assert str(fstat) == "FULFILLMENT_BLOCKED"


@pytest.mark.asyncio
async def test_ingest_all_warehouses_insufficient_does_not_crash(db_session_like_pg, monkeypatch):
    """
    Route C：候选仓库存不足 → FULFILLMENT_BLOCKED（INSUFFICIENT_QTY），不崩溃，且不写 orders.warehouse_id。
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S1"

    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    top_wid, backup_wid = await ensure_two_warehouses(session)
    store_id = await bind_store_warehouses(
        session,
        platform=platform,
        shop_id=shop_id,
        top_warehouse_id=top_wid,
        backup_warehouse_id=backup_wid,
    )

    province = "P-SVC-INS2"
    await ensure_store_province_route(session, store_id=store_id, province=province, warehouse_id=top_wid)

    stock_map = {
        (top_wid, 1): 1,
        (backup_wid, 1): 999,
    }

    async def fake_get_available(self, *_, **kwargs):
        warehouse_id = kwargs.get("warehouse_id")
        item_id = kwargs.get("item_id")
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(StockAvailabilityService, "get_available_for_item", fake_get_available)

    ext_order_no = "E-insufficient-1"
    occurred_at = datetime.now(UTC)

    result = await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        occurred_at=occurred_at,
        buyer_name="王五",
        buyer_phone="13700000000",
        order_amount=50,
        pay_amount=50,
        items=[
            {
                "item_id": 1,
                "sku_id": "SKU-1",
                "title": "库存不足测试商品",
                "qty": 5,
                "price": 10,
                "discount": 0,
                "amount": 50,
            }
        ],
        address={"province": province, "receiver_name": "王五", "receiver_phone": "13700000000"},
        extras={},
        trace_id="TRACE-PH4-003",
    )

    assert result["status"] == "FULFILLMENT_BLOCKED"
    assert isinstance(result.get("route"), dict)
    assert result["route"].get("reason") == "INSUFFICIENT_QTY"

    order_id = result["id"]
    row = await session.execute(
        text("SELECT warehouse_id, fulfillment_status FROM orders WHERE id = :id"),
        {"id": order_id},
    )
    warehouse_id, fstat = row.first()
    assert warehouse_id in (None, 0)
    assert str(fstat) == "FULFILLMENT_BLOCKED"


@pytest.mark.asyncio
async def test_ingest_without_store_warehouse_config_does_not_crash(db_session_like_pg, monkeypatch):
    """
    新世界观语义：店铺无绑定仓 → FULFILLMENT_BLOCKED（NO_WAREHOUSE_BOUND）。
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S-NO-CONFIG"

    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    async def fake_get_available(self, *_, **kwargs):
        return 100

    monkeypatch.setattr(StockAvailabilityService, "get_available_for_item", fake_get_available)

    # 不绑定 store_warehouse，也不写 store_province_routes
    province = "P-NO-MAP-1"
    occurred_at = datetime.now(UTC)

    result = await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no="E-noconfig-1",
        occurred_at=occurred_at,
        buyer_name="赵六",
        buyer_phone="13600000000",
        order_amount=50,
        pay_amount=50,
        items=[
            {
                "item_id": 1,
                "sku_id": "SKU-1",
                "title": "无配置测试商品",
                "qty": 5,
                "price": 10,
                "discount": 0,
                "amount": 50,
            }
        ],
        address={"province": province, "receiver_name": "赵六", "receiver_phone": "13600000000"},
        extras={},
        trace_id="TRACE-PH4-004",
    )

    assert result["status"] == "FULFILLMENT_BLOCKED"
    assert isinstance(result.get("route"), dict)
    assert result["route"].get("reason") == "NO_WAREHOUSE_BOUND"

    order_id = result["id"]
    row = await session.execute(
        text("SELECT warehouse_id, fulfillment_status FROM orders WHERE id = :id"),
        {"id": order_id},
    )
    warehouse_id, fstat = row.first()
    assert warehouse_id in (None, 0)
    assert str(fstat) == "FULFILLMENT_BLOCKED"
