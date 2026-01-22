# tests/services/test_order_multi_store_phase4_routing.py

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

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.services.stock_availability_service import StockAvailabilityService
from app.services.order_service import OrderService

import app.services.order_ingest_service as order_ingest_service

UTC = timezone.utc
pytestmark = pytest.mark.asyncio


async def _ensure_two_warehouses(session):
    """
    返回两个 warehouse_id。
    如果现有仓库数量不足 2 个，则动态插入测试仓（兼容 NOT NULL 无默认值列）。
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

    needed = 2 - len(ids)
    if needed <= 0:
        return ids[0], ids[1]

    cols_rows = await session.execute(
        text(
            """
            SELECT column_name, data_type
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name   = 'warehouses'
               AND is_nullable  = 'NO'
               AND column_default IS NULL
               AND column_name <> 'id'
            """
        )
    )
    col_info = [(str(r[0]), str(r[1])) for r in cols_rows.fetchall()]

    if not col_info:
        for _ in range(needed):
            row = await session.execute(text("INSERT INTO warehouses DEFAULT VALUES RETURNING id"))
            ids.append(int(row.scalar()))
        return ids[0], ids[1]

    columns = ", ".join(c for c, _ in col_info)
    placeholders = ", ".join(f":{c}" for c, _ in col_info)
    sql = f"INSERT INTO warehouses ({columns}) VALUES ({placeholders}) RETURNING id"

    for _ in range(needed):
        params = {}
        for col, dtype in col_info:
            dt = dtype.lower()
            if "char" in dt or "text" in dt:
                params[col] = f"TEST_{col}_{uuid.uuid4().hex[:8]}"
            elif "int" in dt:
                params[col] = 0
            elif "bool" in dt:
                params[col] = False
            elif "timestamp" in dt or "time" in dt:
                params[col] = datetime.now(UTC)
            elif dt == "date":
                params[col] = datetime.now(UTC).date()
            else:
                params[col] = f"TEST_{col}_{uuid.uuid4().hex[:4]}"
        row = await session.execute(text(sql), params)
        ids.append(int(row.scalar()))

    return ids[0], ids[1]


async def _ensure_store(session, platform: str, shop_id: str, name: str) -> int:
    """
    确保 stores(platform, shop_id) 存在，返回 store_id。
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
        {"p": platform.upper(), "s": shop_id},
    )
    store_id = row.scalar()
    if store_id is not None:
        return int(store_id)

    await session.execute(
        text(
            """
            INSERT INTO stores (platform, shop_id, name)
            VALUES (:p, :s, :n)
            ON CONFLICT (platform, shop_id) DO NOTHING
            """
        ),
        {"p": platform.upper(), "s": shop_id, "n": name},
    )
    row2 = await session.execute(
        text(
            """
            SELECT id
              FROM stores
             WHERE platform = :p
               AND shop_id  = :s
             LIMIT 1
            """
        ),
        {"p": platform.upper(), "s": shop_id},
    )
    return int(row2.scalar_one())


async def _bind_store_to_wh(session, store_id: int, wh_id: int, is_top: bool, priority: int) -> None:
    """
    ✅ 统一世界观：store_warehouse 是候选能力声明 + 排序偏好
    """
    # 为了测试可控：每家店只绑定一个仓（避免 fallback_bindings 扩大候选集干扰断言）
    await session.execute(
        text("DELETE FROM store_warehouse WHERE store_id = :sid"),
        {"sid": store_id},
    )
    await session.execute(
        text(
            """
            INSERT INTO store_warehouse (store_id, warehouse_id, is_top, priority)
            VALUES (:sid, :wid, :top, :pr)
            """
        ),
        {"sid": store_id, "wid": int(wh_id), "top": bool(is_top), "pr": int(priority)},
    )


async def _ensure_store_province_route(session, *, store_id: int, province: str, warehouse_id: int) -> None:
    """
    ✅ 统一世界观：store_province_routes = 省 → 候选仓裁剪器
    """
    await session.execute(
        text("DELETE FROM store_province_routes WHERE store_id=:sid AND province=:prov"),
        {"sid": int(store_id), "prov": str(province)},
    )
    await session.execute(
        text(
            """
            INSERT INTO store_province_routes (store_id, province, warehouse_id, priority, active)
            VALUES (:sid, :prov, :wid, 10, TRUE)
            """
        ),
        {"sid": int(store_id), "prov": str(province), "wid": int(warehouse_id)},
    )


@pytest.mark.asyncio
async def test_multi_store_routing_same_platform(db_session_like_pg, monkeypatch):
    """
    同平台下不同店铺、不同省码 → 命中各自候选仓：

    新世界观：
    - 候选集来自 store_province_routes（省 → 候选仓）
    - 候选能力来自 store_warehouse（必须已绑定）
    - 可履约由 StockAvailabilityService 事实裁决
    """
    session = db_session_like_pg
    platform = "PDD"
    shop1 = "S1"
    shop2 = "S2"

    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    async def _noop_reserve_flow(*_, **__):
        return None

    monkeypatch.setattr(order_ingest_service, "reserve_flow", _noop_reserve_flow)

    wh_a, wh_b = await _ensure_two_warehouses(session)
    store1 = await _ensure_store(session, platform, shop1, "Shop 1")
    store2 = await _ensure_store(session, platform, shop2, "Shop 2")

    # 每家店只绑定一个仓，保证候选集不漂移
    await _bind_store_to_wh(session, store_id=store1, wh_id=wh_a, is_top=True, priority=10)
    await _bind_store_to_wh(session, store_id=store2, wh_id=wh_b, is_top=True, priority=10)

    # 省码 → 候选仓（裁剪器）
    prov_a = "P-MULTI-A"
    prov_b = "P-MULTI-B"
    await _ensure_store_province_route(session, store_id=store1, province=prov_a, warehouse_id=wh_a)
    await _ensure_store_province_route(session, store_id=store2, province=prov_b, warehouse_id=wh_b)

    stock_map = {
        (wh_a, 1): 10,
        (wh_b, 1): 10,
    }

    async def fake_get_available(self, *_, **kwargs):
        warehouse_id = kwargs.get("warehouse_id")
        item_id = kwargs.get("item_id")
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(StockAvailabilityService, "get_available_for_item", fake_get_available)

    occurred_at = datetime.now(UTC)

    r1 = await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop1,
        ext_order_no="S1-ORDER-1",
        occurred_at=occurred_at,
        buyer_name="A",
        buyer_phone="111",
        order_amount=50,
        pay_amount=50,
        items=[
            {
                "item_id": 1,
                "sku_id": "SKU-1",
                "title": "S1 商品",
                "qty": 2,
                "price": 25,
                "discount": 0,
                "amount": 50,
            }
        ],
        address={"province": prov_a, "receiver_name": "A", "receiver_phone": "111"},
        extras={},
        trace_id="TRACE-MULTI-S1",
    )
    assert r1["status"] == "OK"
    oid1 = r1["id"]

    r2 = await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop2,
        ext_order_no="S2-ORDER-1",
        occurred_at=occurred_at,
        buyer_name="B",
        buyer_phone="222",
        order_amount=50,
        pay_amount=50,
        items=[
            {
                "item_id": 1,
                "sku_id": "SKU-1",
                "title": "S2 商品",
                "qty": 2,
                "price": 25,
                "discount": 0,
                "amount": 50,
            }
        ],
        address={"province": prov_b, "receiver_name": "B", "receiver_phone": "222"},
        extras={},
        trace_id="TRACE-MULTI-S2",
    )
    assert r2["status"] == "OK"
    oid2 = r2["id"]

    row1 = await session.execute(text("SELECT warehouse_id FROM orders WHERE id = :id"), {"id": oid1})
    wh1 = row1.scalar()

    row2 = await session.execute(text("SELECT warehouse_id FROM orders WHERE id = :id"), {"id": oid2})
    wh2 = row2.scalar()

    assert wh1 == wh_a
    assert wh2 == wh_b
