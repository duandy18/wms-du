# tests/services/test_outbound_sandbox_phase4_routing.py
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.services.stock_availability_service import StockAvailabilityService
from app.services.order_service import OrderService

import app.services.order_ingest_service as order_ingest_service

UTC = timezone.utc
pytestmark = pytest.mark.asyncio


async def _ensure_warehouses(session, n: int) -> list[int]:
    rows = await session.execute(text("SELECT id FROM warehouses ORDER BY id"))
    ids = [int(r[0]) for r in rows.fetchall()]

    needed = n - len(ids)
    if needed <= 0:
        return ids[:n]

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
        return ids[:n]

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
    return ids[:n]


async def _ensure_store(session, platform: str, shop_id: str, name: str, route_mode: str) -> int:
    row = await session.execute(
        text("SELECT id FROM stores WHERE platform=:p AND shop_id=:s LIMIT 1"),
        {"p": platform, "s": shop_id},
    )
    sid = row.scalar()
    if sid is None:
        await session.execute(
            text(
                """
                INSERT INTO stores (platform, shop_id, name, route_mode)
                VALUES (:p, :s, :n, :m)
                ON CONFLICT (platform, shop_id) DO NOTHING
                """
            ),
            {"p": platform, "s": shop_id, "n": name, "m": route_mode},
        )
        row2 = await session.execute(
            text("SELECT id FROM stores WHERE platform=:p AND shop_id=:s LIMIT 1"),
            {"p": platform, "s": shop_id},
        )
        sid = row2.scalar()
    else:
        await session.execute(
            text("UPDATE stores SET route_mode=:m WHERE id=:sid"),
            {"m": route_mode, "sid": sid},
        )
    return int(sid)


async def _bind_store_wh(session, store_id: int, wh_top: int, wh_backup: int):
    """
    ✅ 统一世界观：store_warehouse 是“候选能力声明 + 排序偏好”
    - 省级路由（store_province_routes）要求 route 引用仓必须仍在 store_warehouse 绑定集合里
    - route_c 也会用它做 fallback_bindings 与排序
    """
    await session.execute(
        text("DELETE FROM store_warehouse WHERE store_id=:sid"),
        {"sid": store_id},
    )
    await session.execute(
        text(
            """
            INSERT INTO store_warehouse (store_id, warehouse_id, is_top, priority)
            VALUES (:sid, :wid, TRUE, 10)
            """
        ),
        {"sid": store_id, "wid": wh_top},
    )
    await session.execute(
        text(
            """
            INSERT INTO store_warehouse (store_id, warehouse_id, is_top, priority)
            VALUES (:sid, :wid, FALSE, 20)
            """
        ),
        {"sid": store_id, "wid": wh_backup},
    )


async def _ensure_store_province_route(session, *, store_id: int, province: str, warehouse_id: int) -> None:
    """
    ✅ 统一世界观：省码 → 候选仓裁剪器（store_province_routes）

    约束：
    - route 引用仓必须属于 store_warehouse（我们在 _bind_store_wh 已保证）
    """
    await session.execute(
        text(
            """
            DELETE FROM store_province_routes
             WHERE store_id = :sid
               AND province = :prov
            """
        ),
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
async def test_outbound_sandbox_phase4_routing(db_session_like_pg, monkeypatch):
    """
    Phase 4.x 沙盘（统一选仓世界观）：

    - 候选集：store_province_routes（省 → 候选仓）
    - 偏好：store_warehouse（主/备/priority，仅排序偏好，不承诺可履约）
    - 事实裁决：WarehouseRouter（整单同仓可履约）

    预期：
    - S1：省码命中 wh_a，但库存不足 → FULFILLMENT_BLOCKED（warehouse_id 不写）
    - S2：省码命中 wh_a，但库存不足 → FULFILLMENT_BLOCKED（warehouse_id 不写）
    - S3：省码命中 wh_a，库存足够 → OK（warehouse_id=wh_a）
    """
    session = db_session_like_pg
    platform = "PDD"

    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    async def _noop_reserve_flow(*_, **__):
        return None

    monkeypatch.setattr(order_ingest_service, "reserve_flow", _noop_reserve_flow)

    wh_a, wh_b = await _ensure_warehouses(session, 2)

    s1 = await _ensure_store(session, platform, "S1-FB", "Shop FB", route_mode="FALLBACK")
    s2 = await _ensure_store(session, platform, "S2-ST", "Shop ST", route_mode="STRICT_TOP")
    s3 = await _ensure_store(session, platform, "S3-FBOK", "Shop FB-OK", route_mode="FALLBACK")

    await _bind_store_wh(session, s1, wh_a, wh_b)
    await _bind_store_wh(session, s2, wh_a, wh_b)
    await _bind_store_wh(session, s3, wh_a, wh_b)

    # ✅ 统一世界观：三家店各用一个省码，省级路由都命中候选仓 wh_a
    prov_s1 = "P-OS-S1"
    prov_s2 = "P-OS-S2"
    prov_s3 = "P-OS-S3"
    await _ensure_store_province_route(session, store_id=s1, province=prov_s1, warehouse_id=wh_a)
    await _ensure_store_province_route(session, store_id=s2, province=prov_s2, warehouse_id=wh_a)
    await _ensure_store_province_route(session, store_id=s3, province=prov_s3, warehouse_id=wh_a)

    stock_map = {
        (wh_a, 1, "S1-FB"): 2,  # 不足
        (wh_b, 1, "S1-FB"): 10,  # 有货（不影响，候选集只有 wh_a）
        (wh_a, 1, "S2-ST"): 2,  # 不足
        (wh_b, 1, "S2-ST"): 10,  # 有货（不影响）
        (wh_a, 1, "S3-FBOK"): 10,  # 足够
        (wh_b, 1, "S3-FBOK"): 0,
    }

    async def fake_get_available(session, platform, shop_id, warehouse_id, item_id) -> int:
        key = (int(warehouse_id), int(item_id), str(shop_id))
        return int(stock_map.get(key, 0))

    monkeypatch.setattr(StockAvailabilityService, "get_available_for_item", fake_get_available)

    async def _place(platform: str, shop_id: str, ext: str, province: str) -> dict:
        return await OrderService.ingest(
            session,
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext,
            occurred_at=datetime.now(UTC),
            buyer_name=f"Buyer-{shop_id}",
            buyer_phone="000",
            order_amount=50,
            pay_amount=50,
            items=[
                {
                    "item_id": 1,
                    "sku_id": "SKU-1",
                    "title": f"ITEM-{shop_id}",
                    "qty": 5,
                    "price": 10,
                    "discount": 0,
                    "amount": 50,
                }
            ],
            address={"province": province, "receiver_name": "X", "receiver_phone": "000"},
            extras={},
            trace_id=f"TRACE-SANDBOX-{shop_id}",
        )

    r1 = await _place(platform, "S1-FB", "ORD-S1-001", prov_s1)
    r2 = await _place(platform, "S2-ST", "ORD-S2-001", prov_s2)
    r3 = await _place(platform, "S3-FBOK", "ORD-S3-001", prov_s3)

    assert r1["status"] == "FULFILLMENT_BLOCKED"
    assert r2["status"] == "FULFILLMENT_BLOCKED"
    assert r3["status"] == "OK"

    oid1 = int(r1["id"])
    oid2 = int(r2["id"])
    oid3 = int(r3["id"])

    row = await session.execute(text("SELECT warehouse_id FROM orders WHERE id=:id"), {"id": oid1})
    wh1 = row.scalar()
    row = await session.execute(text("SELECT warehouse_id FROM orders WHERE id=:id"), {"id": oid2})
    wh2 = row.scalar()
    row = await session.execute(text("SELECT warehouse_id FROM orders WHERE id=:id"), {"id": oid3})
    wh3 = row.scalar()

    # S1：候选仓不足 → BLOCKED → warehouse_id 不写
    assert wh1 in (None, 0)

    # S2：候选仓不足 → BLOCKED → warehouse_id 不写
    assert wh2 in (None, 0)

    # S3：候选仓足够 → READY → warehouse_id = wh_a
    assert wh3 == wh_a
