# tests/services/test_order_service_phase4_routing.py
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.services.channel_inventory_service import ChannelInventoryService
from app.services.order_service import OrderService


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

    策略：
      - 先读取现有 warehouses；
      - 若不足 2 个，则用最小合法 INSERT 语句补齐：
          INSERT INTO warehouses (name) VALUES (:name) RETURNING id
      - 不再动态 introspect 所有列，只保证 name 非空即可。
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
    把给定的两个仓绑定到指定店铺：
    - 清空原有 store_warehouse 记录
    - top_warehouse_id 作为 is_top = true
    - backup_warehouse_id 作为 is_top = false
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


@pytest.mark.asyncio
async def test_ingest_routes_to_top_warehouse_when_in_stock(db_session_like_pg, monkeypatch):
    """
    极简语义 1：主仓库存足够时，应路由到主仓，并写入 orders.warehouse_id。
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S1"

    top_wid, backup_wid = await _pick_two_warehouses(session)
    await _bind_store_warehouses(
        session,
        platform=platform,
        shop_id=shop_id,
        top_warehouse_id=top_wid,
        backup_warehouse_id=backup_wid,
    )

    # 主仓与备仓都有足够库存
    stock_map = {
        (top_wid, 1): 10,
        (backup_wid, 1): 10,
    }

    async def fake_get_available(self, *_, **kwargs):
        warehouse_id = kwargs.get("warehouse_id")
        item_id = kwargs.get("item_id")
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(
        ChannelInventoryService,
        "get_available_for_item",
        fake_get_available,
    )

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
        address={"receiver_name": "张三", "receiver_phone": "13800000000"},
        extras={},
        trace_id="TRACE-PH4-001",
    )

    assert result["status"] == "OK"
    order_id = result["id"]

    row = await session.execute(
        text("SELECT warehouse_id FROM orders WHERE id = :id"),
        {"id": order_id},
    )
    warehouse_id = row.scalar()
    assert warehouse_id == top_wid


@pytest.mark.asyncio
async def test_ingest_routes_to_backup_when_top_insufficient(
    db_session_like_pg, monkeypatch
):
    """
    极简语义 2（FALLBACK 模式）：

    - 主仓库存不足；
    - 备仓库存足够；
    - 默认 route_mode=FALLBACK 下，应自动 fallback 到备仓。
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S1"

    top_wid, backup_wid = await _pick_two_warehouses(session)
    await _bind_store_warehouses(
        session,
        platform=platform,
        shop_id=shop_id,
        top_warehouse_id=top_wid,
        backup_warehouse_id=backup_wid,
    )

    stock_map = {
        (top_wid, 1): 2,   # 主仓不够
        (backup_wid, 1): 10,  # 备仓足够
    }

    async def fake_get_available(self, *_, **kwargs):
        warehouse_id = kwargs.get("warehouse_id")
        item_id = kwargs.get("item_id")
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(
        ChannelInventoryService,
        "get_available_for_item",
        fake_get_available,
    )

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
        address={"receiver_name": "李四", "receiver_phone": "13900000000"},
        extras={},
        trace_id="TRACE-PH4-002",
    )

    assert result["status"] == "OK"
    order_id = result["id"]

    row = await session.execute(
        text("SELECT warehouse_id FROM orders WHERE id = :id"),
        {"id": order_id},
    )
    warehouse_id = row.scalar()
    # 当前业务语义：fallback 模式下，应路由到备仓
    assert warehouse_id == backup_wid


@pytest.mark.asyncio
async def test_ingest_all_warehouses_insufficient_does_not_crash(db_session_like_pg, monkeypatch):
    """
    极简语义 3：所有仓库存都不足时，不崩溃，但也不写入仓（保持 NULL/0）。
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S1"

    top_wid, backup_wid = await _pick_two_warehouses(session)
    await _bind_store_warehouses(
        session,
        platform=platform,
        shop_id=shop_id,
        top_warehouse_id=top_wid,
        backup_warehouse_id=backup_wid,
    )

    stock_map = {
        (top_wid, 1): 1,
        (backup_wid, 1): 3,
    }

    async def fake_get_available(self, *_, **kwargs):
        warehouse_id = kwargs.get("warehouse_id")
        item_id = kwargs.get("item_id")
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(
        ChannelInventoryService,
        "get_available_for_item",
        fake_get_available,
    )

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
        address={"receiver_name": "王五", "receiver_phone": "13700000000"},
        extras={},
        trace_id="TRACE-PH4-003",
    )

    assert result["status"] == "OK"
    order_id = result["id"]

    row = await session.execute(
        text("SELECT warehouse_id FROM orders WHERE id = :id"),
        {"id": order_id},
    )
    warehouse_id = row.scalar()
    assert warehouse_id in (None, 0)


@pytest.mark.asyncio
async def test_ingest_without_store_warehouse_config_does_not_crash(
    db_session_like_pg, monkeypatch
):
    """
    极简语义 4：该店铺完全没有 store_warehouse 配置时，
    订单正常创建，只是不写入 warehouse_id（保持 NULL/0）。
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S-NO-CONFIG"

    async def fake_get_available(self, *_, **kwargs):
        # 代表“库存足够”，实际路由逻辑会发现没有 store_warehouse 绑定
        return 100

    monkeypatch.setattr(
        ChannelInventoryService,
        "get_available_for_item",
        fake_get_available,
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
        address={"receiver_name": "赵六", "receiver_phone": "13600000000"},
        extras={},
        trace_id="TRACE-PH4-004",
    )

    assert result["status"] == "OK"
    order_id = result["id"]

    row = await session.execute(
        text("SELECT warehouse_id FROM orders WHERE id = :id"),
        {"id": order_id},
    )
    warehouse_id = row.scalar()
    assert warehouse_id in (None, 0)
