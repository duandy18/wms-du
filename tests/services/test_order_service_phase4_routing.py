# tests/services/test_order_service_phase4_routing.py
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.services.channel_inventory_service import ChannelInventoryService
from app.services.order_service import OrderService

import app.services.order_ingest_service as order_ingest_service


UTC = timezone.utc
pytestmark = pytest.mark.asyncio


async def _get_store_id_for_shop(session, platform: str, shop_id: str) -> int:
    """
    从 stores 表按 (platform, shop_id) 找到 store_id。
    """
    row = await session.execute(
        text(
            """
            SELECT id
              FROM stores
             WHERE platform = :p
               AND shop_id  = :s
             LIMIT 1
            """
        ),
        {"p": platform, "s": shop_id},
    )
    store_id = row.scalar()
    assert store_id is not None, f"test precondition failed: no store for {platform}/{shop_id}"
    return int(store_id)


async def _pick_two_warehouses(session):
    """
    返回两个 warehouse_id，作为主仓 / 备仓。
    """
    rows = await session.execute(
        text(
            """
            SELECT id
              FROM warehouses
             ORDER BY id
            """
        )
    )
    ids = [int(r[0]) for r in rows.fetchall()]

    while len(ids) < 2:
        name = f"AUTO-WH-{uuid.uuid4().hex[:8]}"
        row = await session.execute(
            text("INSERT INTO warehouses (name) VALUES (:name) RETURNING id"),
            {"name": name},
        )
        ids.append(int(row.scalar()))

    return ids[0], ids[1]


async def _bind_store_warehouses(
    session,
    *,
    platform: str,
    shop_id: str,
    top_warehouse_id: int,
    backup_warehouse_id: int,
):
    """
    legacy 配置保留：Route C 不使用 store_warehouse，但保留不会影响测试。
    """
    store_id = await _get_store_id_for_shop(session, platform, shop_id)

    await session.execute(
        text(
            """
            DELETE FROM store_warehouse
             WHERE store_id = :sid
            """
        ),
        {"sid": store_id},
    )

    await session.execute(
        text(
            """
            INSERT INTO store_warehouse (store_id, warehouse_id, is_top, priority)
            VALUES (:sid, :wid, :top, :pr)
            """
        ),
        {"sid": store_id, "wid": top_warehouse_id, "top": True, "pr": 10},
    )

    await session.execute(
        text(
            """
            INSERT INTO store_warehouse (store_id, warehouse_id, is_top, priority)
            VALUES (:sid, :wid, :top, :pr)
            """
        ),
        {"sid": store_id, "wid": backup_warehouse_id, "top": False, "pr": 1},
    )


async def _ensure_service_province(session, *, province_code: str, warehouse_id: int) -> None:
    await session.execute(
        text("DELETE FROM warehouse_service_provinces WHERE province_code = :p"),
        {"p": province_code},
    )
    await session.execute(
        text(
            """
            INSERT INTO warehouse_service_provinces (warehouse_id, province_code)
            VALUES (:wid, :p)
            """
        ),
        {"wid": int(warehouse_id), "p": province_code},
    )


@pytest.mark.asyncio
async def test_ingest_routes_to_top_warehouse_when_in_stock(db_session_like_pg, monkeypatch):
    """
    Route C 语义 1：服务仓库存足够时，应命中服务仓并写入 orders.warehouse_id（READY_TO_FULFILL）。
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S1"

    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    # 避免测试把“路由”与“预占”耦在一起：reserve_flow no-op
    async def _noop_reserve_flow(*_, **__):
        return None

    monkeypatch.setattr(order_ingest_service, "reserve_flow", _noop_reserve_flow)

    top_wid, backup_wid = await _pick_two_warehouses(session)
    await _bind_store_warehouses(
        session,
        platform=platform,
        shop_id=shop_id,
        top_warehouse_id=top_wid,
        backup_warehouse_id=backup_wid,
    )

    province = "P-SVC-TOP"
    await _ensure_service_province(session, province_code=province, warehouse_id=top_wid)

    stock_map = {
        (top_wid, 1): 10,
        (backup_wid, 1): 10,
    }

    async def fake_get_available(self, *_, **kwargs):
        warehouse_id = kwargs.get("warehouse_id")
        item_id = kwargs.get("item_id")
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(ChannelInventoryService, "get_available_for_item", fake_get_available)

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

    Route C 新事实：不兜底，不选仓；服务仓不足 → FULFILLMENT_BLOCKED（INSUFFICIENT_QTY）。
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S1"

    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    top_wid, backup_wid = await _pick_two_warehouses(session)
    await _bind_store_warehouses(
        session,
        platform=platform,
        shop_id=shop_id,
        top_warehouse_id=top_wid,
        backup_warehouse_id=backup_wid,
    )

    province = "P-SVC-INS1"
    await _ensure_service_province(session, province_code=province, warehouse_id=top_wid)

    stock_map = {
        (top_wid, 1): 2,      # 服务仓不够
        (backup_wid, 1): 10,  # 备仓足够（Route C 不看）
    }

    async def fake_get_available(self, *_, **kwargs):
        warehouse_id = kwargs.get("warehouse_id")
        item_id = kwargs.get("item_id")
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(ChannelInventoryService, "get_available_for_item", fake_get_available)

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
        text("SELECT warehouse_id, service_warehouse_id, fulfillment_status FROM orders WHERE id = :id"),
        {"id": order_id},
    )
    whid, swid, fstat = row.first()
    assert whid in (None, 0)
    assert int(swid) == int(top_wid)
    assert str(fstat) == "FULFILLMENT_BLOCKED"


@pytest.mark.asyncio
async def test_ingest_all_warehouses_insufficient_does_not_crash(db_session_like_pg, monkeypatch):
    """
    Route C 语义：服务仓库存不足 → FULFILLMENT_BLOCKED（INSUFFICIENT_QTY），不崩溃，且不写 orders.warehouse_id。
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S1"

    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    top_wid, backup_wid = await _pick_two_warehouses(session)
    await _bind_store_warehouses(
        session,
        platform=platform,
        shop_id=shop_id,
        top_warehouse_id=top_wid,
        backup_warehouse_id=backup_wid,
    )

    province = "P-SVC-INS2"
    await _ensure_service_province(session, province_code=province, warehouse_id=top_wid)

    stock_map = {
        (top_wid, 1): 1,
        (backup_wid, 1): 999,
    }

    async def fake_get_available(self, *_, **kwargs):
        warehouse_id = kwargs.get("warehouse_id")
        item_id = kwargs.get("item_id")
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(ChannelInventoryService, "get_available_for_item", fake_get_available)

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
    Route C 语义：无服务仓配置（省未映射）→ FULFILLMENT_BLOCKED（NO_SERVICE_WAREHOUSE），不崩溃，且不写 orders.warehouse_id。

    注意：store_warehouse 配置在 Route C 不参与决策。
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S-NO-CONFIG"

    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    # 代表“库存足够”，但 Route C 会先卡在“无服务仓映射”
    async def fake_get_available(self, *_, **kwargs):
        return 100

    monkeypatch.setattr(ChannelInventoryService, "get_available_for_item", fake_get_available)

    # 使用一个“测试专用省码”，确保未配置服务仓
    province = "P-NO-MAP-1"
    await session.execute(
        text("DELETE FROM warehouse_service_provinces WHERE province_code = :p"),
        {"p": province},
    )

    ext_order_no = "E-noconfig-1"
    occurred_at = datetime.now(UTC)

    result = await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
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
    assert result["route"].get("reason") == "NO_SERVICE_WAREHOUSE"

    order_id = result["id"]
    row = await session.execute(
        text("SELECT warehouse_id, fulfillment_status FROM orders WHERE id = :id"),
        {"id": order_id},
    )
    warehouse_id, fstat = row.first()
    assert warehouse_id in (None, 0)
    assert str(fstat) == "FULFILLMENT_BLOCKED"
