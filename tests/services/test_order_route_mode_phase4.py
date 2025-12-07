# tests/services/test_order_route_mode_phase4.py
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

    # 动态补充 NOT NULL 且无默认值的列
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
                params[col] = f"WH-{col}-{uuid.uuid4().hex[:8]}"
            elif "int" in dt:
                params[col] = 0
            elif "bool" in dt:
                params[col] = False
            elif "timestamp" in dt or "time" in dt:
                params[col] = datetime.now(UTC)
            elif dt == "date":
                params[col] = datetime.now(UTC).date()
            else:
                params[col] = f"WH-{col}-{uuid.uuid4().hex[:4]}"
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


async def _bind_store_wh(session, store_id: int, top_wh: int, backup_wh: int):
    await session.execute(
        text("DELETE FROM store_warehouse WHERE store_id = :sid"),
        {"sid": store_id},
    )
    await session.execute(
        text(
            """
            INSERT INTO store_warehouse (store_id, warehouse_id, is_top, priority)
            VALUES (:sid, :wid, TRUE, 10)
            """
        ),
        {"sid": store_id, "wid": top_wh},
    )
    await session.execute(
        text(
            """
            INSERT INTO store_warehouse (store_id, warehouse_id, is_top, priority)
            VALUES (:sid, :wid, FALSE, 20)
            """
        ),
        {"sid": store_id, "wid": backup_wh},
    )


@pytest.mark.asyncio
async def test_route_mode_fallback_uses_backup(db_session_like_pg, monkeypatch):
    """
    FALLBACK 模式下：主仓库存不足时，应 fallback 到备仓。
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S-FB"

    top_wh, backup_wh = await _ensure_two_warehouses(session)
    store_id = await _ensure_store(session, platform, shop_id, "FB-STORE")

    await _bind_store_wh(session, store_id, top_wh, backup_wh)

    # 显式设为 FALLBACK（虽然默认就是）
    await session.execute(
        text("UPDATE stores SET route_mode='FALLBACK' WHERE id=:sid"),
        {"sid": store_id},
    )

    stock_map = {
        (top_wh, 1): 2,  # 主仓不够
        (backup_wh, 1): 10,  # 备仓足够
    }

    async def fake_get_available(self, session_, platform_, shop_id_, warehouse_id, item_id):
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(ChannelInventoryService, "get_available_for_item", fake_get_available)

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
        address={"receiver_name": "A", "receiver_phone": "111"},
        extras={},
        trace_id="TRACE-FB-1",
    )

    assert res["status"] == "OK"
    oid = res["id"]

    row = await session.execute(
        text("SELECT warehouse_id FROM orders WHERE id=:id"),
        {"id": oid},
    )
    wid = row.scalar()
    # FALLBACK 模式下，应选择备仓
    assert wid == backup_wh


@pytest.mark.asyncio
async def test_route_mode_strict_top_does_not_fallback(db_session_like_pg, monkeypatch):
    """
    STRICT_TOP 模式下：主仓库存不足时，不使用备仓，订单不选仓（warehouse_id 为空/0）。
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S-STRICT"

    top_wh, backup_wh = await _ensure_two_warehouses(session)
    store_id = await _ensure_store(session, platform, shop_id, "STRICT-STORE")

    await _bind_store_wh(session, store_id, top_wh, backup_wh)

    await session.execute(
        text("UPDATE stores SET route_mode='STRICT_TOP' WHERE id=:sid"),
        {"sid": store_id},
    )

    stock_map = {
        (top_wh, 1): 2,  # 主仓不够
        (backup_wh, 1): 10,  # 备仓足够，但 STRICT_TOP 模式下应该“看不见”
    }

    async def fake_get_available(self, session_, platform_, shop_id_, warehouse_id, item_id):
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(ChannelInventoryService, "get_available_for_item", fake_get_available)

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
        address={"receiver_name": "B", "receiver_phone": "222"},
        extras={},
        trace_id="TRACE-ST-1",
    )

    assert res["status"] == "OK"
    oid = res["id"]

    row = await session.execute(
        text("SELECT warehouse_id FROM orders WHERE id=:id"),
        {"id": oid},
    )
    wid = row.scalar()
    # STRICT_TOP：主仓不够 → 不 fallback → 不选仓
    assert wid in (None, 0)
