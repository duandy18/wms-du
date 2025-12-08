# tests/services/test_order_multi_store_phase4_routing.py
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.services.channel_inventory_service import ChannelInventoryService
from app.services.order_service import OrderService

UTC = timezone.utc
pytestmark = pytest.mark.asyncio


async def _ensure_two_warehouses(session):
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
    if store_id is not None:
        return int(store_id)

    # 动态填充 NOT NULL 且无默认值的列
    cols_rows = await session.execute(
        text(
            """
            SELECT column_name, data_type
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name   = 'stores'
               AND is_nullable  = 'NO'
               AND column_default IS NULL
               AND column_name <> 'id'
            """
        )
    )
    col_info = [(str(r[0]), str(r[1])) for r in cols_rows.fetchall()]

    # 如果没有特殊 NOT NULL 列，就只插 platform/shop_id/name
    if not col_info:
        ins = await session.execute(
            text(
                """
                INSERT INTO stores (platform, shop_id, name)
                VALUES (:p, :s, :n)
                ON CONFLICT (platform, shop_id) DO NOTHING
                RETURNING id
                """
            ),
            {"p": platform, "s": shop_id, "n": name},
        )
        sid = ins.scalar_one_or_none()
        if sid is not None:
            return int(sid)
        row2 = await session.execute(
            text(
                """
                SELECT id FROM stores WHERE platform=:p AND shop_id=:s LIMIT 1
                """
            ),
            {"p": platform, "s": shop_id},
        )
        return int(row2.scalar_one())

    # 有额外 NOT NULL 列：构造插入
    # 强制包含 platform/shop_id/name，其他列按类型生成 dummy 值
    columns = ["platform", "shop_id", "name"]
    params: dict[str, object] = {
        "platform": platform,
        "shop_id": shop_id,
        "name": name,
    }

    for col, dtype in col_info:
        if col in ("platform", "shop_id", "name"):
            continue
        dt = dtype.lower()
        columns.append(col)
        if "char" in dt or "text" in dt:
            params[col] = f"{col}-{uuid.uuid4().hex[:6]}"
        elif "int" in dt:
            params[col] = 0
        elif "bool" in dt:
            params[col] = False
        elif "timestamp" in dt or "time" in dt:
            params[col] = datetime.now(UTC)
        elif dt == "date":
            params[col] = datetime.now(UTC).date()
        else:
            params[col] = f"{col}-{uuid.uuid4().hex[:4]}"

    col_sql = ", ".join(columns)
    val_sql = ", ".join(f":{c}" for c in columns)
    sql = f"""
        INSERT INTO stores ({col_sql})
        VALUES ({val_sql})
        ON CONFLICT (platform, shop_id) DO NOTHING
        RETURNING id
    """

    ins = await session.execute(text(sql), params)
    sid = ins.scalar_one_or_none()
    if sid is not None:
        return int(sid)

    row2 = await session.execute(
        text("SELECT id FROM stores WHERE platform=:p AND shop_id=:s LIMIT 1"),
        {"p": platform, "s": shop_id},
    )
    return int(row2.scalar_one())


async def _bind_store_to_wh(
    session, store_id: int, wh_id: int, is_top: bool, priority: int
) -> None:
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
        {"sid": store_id, "wid": wh_id, "top": is_top, "pr": priority},
    )


@pytest.mark.asyncio
async def test_multi_store_routing_same_platform(db_session_like_pg, monkeypatch):
    """
    同平台 PDD 下，S1 / S2 分别绑定不同主仓时：
    - S1 订单应路由到 wh_a
    - S2 订单应路由到 wh_b
    """
    session = db_session_like_pg
    platform = "PDD"
    shop1 = "S1"
    shop2 = "S2"

    wh_a, wh_b = await _ensure_two_warehouses(session)
    store1 = await _ensure_store(session, platform, shop1, "Shop 1")
    store2 = await _ensure_store(session, platform, shop2, "Shop 2")

    await _bind_store_to_wh(session, store_id=store1, wh_id=wh_a, is_top=True, priority=10)
    await _bind_store_to_wh(session, store_id=store2, wh_id=wh_b, is_top=True, priority=10)

    # 路由可用库存：两个仓对 item 1 均有足够可用量
    stock_map = {
        (wh_a, 1): 10,
        (wh_b, 1): 10,
    }

    async def fake_get_available(self, *_, **kwargs):
        warehouse_id = kwargs.get("warehouse_id")
        item_id = kwargs.get("item_id")
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(ChannelInventoryService, "get_available_for_item", fake_get_available)

    occurred_at = datetime.now(UTC)

    # S1 订单
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
        address={"receiver_name": "A", "receiver_phone": "111"},
        extras={},
        trace_id="TRACE-MULTI-S1",
    )
    assert r1["status"] == "OK"
    oid1 = r1["id"]

    # S2 订单
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
        address={"receiver_name": "B", "receiver_phone": "222"},
        extras={},
        trace_id="TRACE-MULTI-S2",
    )
    assert r2["status"] == "OK"
    oid2 = r2["id"]

    # 检查 orders.warehouse_id
    row1 = await session.execute(
        text("SELECT warehouse_id FROM orders WHERE id = :id"),
        {"id": oid1},
    )
    wh1 = row1.scalar()
    row2 = await session.execute(
        text("SELECT warehouse_id FROM orders WHERE id = :id"),
        {"id": oid2},
    )
    wh2 = row2.scalar()

    assert wh1 == wh_a
    assert wh2 == wh_b
