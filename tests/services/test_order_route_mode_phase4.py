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
    # legacy 配置保留：Route C 不使用 store_warehouse，但保留不会影响测试
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


async def _ensure_service_province(session, *, province_code: str, warehouse_id: int) -> None:
    # Route C：省→唯一服务仓
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
async def test_route_mode_fallback_uses_backup(db_session_like_pg, monkeypatch):
    """
    旧 Phase4 语义：FALLBACK 模式下主仓不足应 fallback 到备仓。

    Route C 新事实：
    - 不兜底、不选仓；只命中“省→服务仓”
    - 即便“备仓可用”，也不会 fallback
    - 服务仓库存不足 → FULFILLMENT_BLOCKED（INSUFFICIENT_QTY），orders.warehouse_id 不写
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S-FB"

    # 禁止测试辅助 fallback（让省份来源必须来自 address）
    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    top_wh, backup_wh = await _ensure_two_warehouses(session)
    store_id = await _ensure_store(session, platform, shop_id, "FB-STORE")
    await _bind_store_wh(session, store_id, top_wh, backup_wh)

    # legacy：显式设为 FALLBACK（Route C 不使用）
    await session.execute(
        text("UPDATE stores SET route_mode='FALLBACK' WHERE id=:sid"),
        {"sid": store_id},
    )

    # Route C：省命中服务仓 = top_wh
    province = "P-FB"
    await _ensure_service_province(session, province_code=province, warehouse_id=top_wh)

    stock_map = {
        (top_wh, 1): 2,      # 服务仓不够
        (backup_wh, 1): 10,  # 备仓足够（Route C 也不会看）
    }

    async def fake_get_available(self, *_, **kwargs):
        warehouse_id = kwargs.get("warehouse_id")
        item_id = kwargs.get("item_id")
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
        address={"province": province, "receiver_name": "A", "receiver_phone": "111"},
        extras={},
        trace_id="TRACE-FB-1",
    )

    assert res["status"] == "FULFILLMENT_BLOCKED"
    assert isinstance(res.get("route"), dict)
    assert res["route"].get("reason") == "INSUFFICIENT_QTY"
    assert res["route"].get("service_warehouse_id") == int(top_wh)

    oid = res["id"]
    row = await session.execute(
        text("SELECT warehouse_id, service_warehouse_id, fulfillment_status FROM orders WHERE id=:id"),
        {"id": oid},
    )
    whid, swid, fstat = row.first()
    assert whid in (None, 0)
    assert int(swid) == int(top_wh)
    assert str(fstat) == "FULFILLMENT_BLOCKED"


@pytest.mark.asyncio
async def test_route_mode_strict_top_does_not_fallback(db_session_like_pg, monkeypatch):
    """
    旧 Phase4 语义：STRICT_TOP 模式下主仓不足，不 fallback，warehouse_id 为空。

    Route C 新事实：
    - route_mode 不参与决策
    - 省命中服务仓后，仅做“整单能否履约”校验
    - 库存不足 → FULFILLMENT_BLOCKED（INSUFFICIENT_QTY），orders.warehouse_id 不写
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S-STRICT"

    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    top_wh, backup_wh = await _ensure_two_warehouses(session)
    store_id = await _ensure_store(session, platform, shop_id, "STRICT-STORE")
    await _bind_store_wh(session, store_id, top_wh, backup_wh)

    await session.execute(
        text("UPDATE stores SET route_mode='STRICT_TOP' WHERE id=:sid"),
        {"sid": store_id},
    )

    province = "P-STRICT"
    await _ensure_service_province(session, province_code=province, warehouse_id=top_wh)

    stock_map = {
        (top_wh, 1): 2,
        (backup_wh, 1): 10,
    }

    async def fake_get_available(self, *_, **kwargs):
        warehouse_id = kwargs.get("warehouse_id")
        item_id = kwargs.get("item_id")
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
        address={"province": province, "receiver_name": "B", "receiver_phone": "222"},
        extras={},
        trace_id="TRACE-ST-1",
    )

    assert res["status"] == "FULFILLMENT_BLOCKED"
    assert isinstance(res.get("route"), dict)
    assert res["route"].get("reason") == "INSUFFICIENT_QTY"
    assert res["route"].get("service_warehouse_id") == int(top_wh)

    oid = res["id"]
    row = await session.execute(
        text("SELECT warehouse_id, service_warehouse_id, fulfillment_status FROM orders WHERE id=:id"),
        {"id": oid},
    )
    whid, swid, fstat = row.first()
    assert whid in (None, 0)
    assert int(swid) == int(top_wh)
    assert str(fstat) == "FULFILLMENT_BLOCKED"
