import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.services.channel_inventory_service import ChannelInventoryService
from app.services.order_service import OrderService


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

    如果当前 warehouses 表里的数量不足 2 个，则在测试里动态插入测试仓：
    - 通过 information_schema.columns 探测 NOT NULL 且无默认值的列；
    - 对这些列填入 dummy 值（字符串列用随机后缀，int 用 0，时间列用 now 等）；
    - 这样不会触碰业务迁移逻辑，也不会依赖全局 seed。

    最终保证返回的列表长度 >= 2。
    """
    # 先取已有仓
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

    # 查找 NOT NULL 且没有默认值的列（排除 id）
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

    # 如果没有这种列，说明 DEFAULT VALUES 就足够（极端情况）
    if not col_info:
        for _ in range(needed):
            row = await session.execute(text("INSERT INTO warehouses DEFAULT VALUES RETURNING id"))
            ids.append(int(row.scalar()))
        return ids[0], ids[1]

    # 构造 INSERT 语句
    columns = ", ".join(c for c, _ in col_info)
    placeholders = ", ".join(f":{c}" for c, _ in col_info)
    sql = f"INSERT INTO warehouses ({columns}) VALUES ({placeholders}) RETURNING id"

    for _ in range(needed):
        params = {}
        for col, dtype in col_info:
            dt = dtype.lower()
            # 字符串类：用随机字符串避免唯一冲突
            if "char" in dt or "text" in dt:
                params[col] = f"TEST_{col}_{uuid.uuid4().hex[:8]}"
            # 整型
            elif "int" in dt:
                params[col] = 0
            # 布尔
            elif "bool" in dt:
                params[col] = False
            # 时间戳 / 时间
            elif "timestamp" in dt or "time" in dt:
                params[col] = datetime.now(timezone.utc)
            elif dt == "date":
                params[col] = datetime.now(timezone.utc).date()
            # 兜底
            else:
                params[col] = f"TEST_{col}_{uuid.uuid4().hex[:4]}"

        row = await session.execute(text(sql), params)
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

    stock_map = {
        (top_wid, 1): 10,
        (backup_wid, 1): 10,
    }

    async def fake_get_available(self, session_, platform_, shop_id_, warehouse_id, item_id):
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(
        ChannelInventoryService,
        "get_available_for_item",
        fake_get_available,
    )

    ext_order_no = "E-top-1"
    occurred_at = datetime.now(timezone.utc)

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
async def test_ingest_does_not_route_to_backup_when_top_insufficient(
    db_session_like_pg, monkeypatch
):
    """
    极简语义 2：

    - 主仓库存不足；
    - 备仓库存足够；
    - 系统 **不** 自动 fallback 到备仓，只在主仓可满足整单时自动写入 warehouse_id。
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
        (top_wid, 1): 2,  # 主仓不够
        (backup_wid, 1): 10,
    }

    async def fake_get_available(self, session_, platform_, shop_id_, warehouse_id, item_id):
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(
        ChannelInventoryService,
        "get_available_for_item",
        fake_get_available,
    )

    ext_order_no = "E-backup-1"
    occurred_at = datetime.now(timezone.utc)

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
    # 极简语义：主仓不够时不自动选备仓，由人工/上层决定
    assert warehouse_id in (None, 0)


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

    async def fake_get_available(self, session_, platform_, shop_id_, warehouse_id, item_id):
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(
        ChannelInventoryService,
        "get_available_for_item",
        fake_get_available,
    )

    ext_order_no = "E-insufficient-1"
    occurred_at = datetime.now(timezone.utc)

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

    async def fake_get_available(self, session_, platform_, shop_id_, warehouse_id, item_id):
        return 100

    monkeypatch.setattr(
        ChannelInventoryService,
        "get_available_for_item",
        fake_get_available,
    )

    ext_order_no = "E-noconfig-1"
    occurred_at = datetime.now(timezone.utc)

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
