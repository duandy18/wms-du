# tests/api/test_v2_full_chain.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_service import OrderService
from app.services.stock.lots import ensure_lot_full
from app.services.stock_service import StockService


async def _ensure_store_route_to_wh1(session: AsyncSession, *, plat: str, shop_id: str, province: str) -> None:
    """
    该 helper 保留用于历史/可读性：配置 store_warehouse + store_province_routes。
    Phase 5 的服务归属命中依赖 warehouse_service_provinces(/cities)，与 store_province_routes 无关。
    """
    await session.execute(
        text(
            """
            INSERT INTO stores (platform, shop_id, name)
            VALUES (:p,:s,:n)
            ON CONFLICT (platform, shop_id) DO NOTHING
            """
        ),
        {"p": plat.upper(), "s": shop_id, "n": f"UT-{plat.upper()}-{shop_id}"},
    )
    row = await session.execute(
        text("SELECT id FROM stores WHERE platform=:p AND shop_id=:s LIMIT 1"),
        {"p": plat.upper(), "s": shop_id},
    )
    store_id = int(row.scalar_one())

    # 绑定仓 1
    await session.execute(
        text(
            """
            INSERT INTO store_warehouse (store_id, warehouse_id, is_top, priority)
            VALUES (:sid, 1, TRUE, 10)
            ON CONFLICT (store_id, warehouse_id) DO NOTHING
            """
        ),
        {"sid": store_id},
    )

    # 省路由 → 仓 1（仅为兼容旧测试数据，不作为主线依赖）
    await session.execute(
        text("DELETE FROM store_province_routes WHERE store_id=:sid AND province=:prov"),
        {"sid": store_id, "prov": province},
    )
    await session.execute(
        text(
            """
            INSERT INTO store_province_routes (store_id, province, warehouse_id, priority, active)
            VALUES (:sid, :prov, 1, 10, TRUE)
            """
        ),
        {"sid": store_id, "prov": province},
    )


async def _ensure_supplier_lot(session: AsyncSession, *, wh_id: int, item_id: int, lot_code: str) -> int:
    """
    Lot-World 终态：
    - SUPPLIER lot identity = (warehouse_id,item_id,lot_code_key)
    - partial unique index: UNIQUE(warehouse_id,item_id,lot_code_key) WHERE lot_code IS NOT NULL
    因此测试侧必须走统一入口 ensure_lot_full（避免散装 ON CONFLICT 写错）。
    """
    return await ensure_lot_full(
        session,
        item_id=int(item_id),
        warehouse_id=int(wh_id),
        lot_code=str(lot_code),
        production_date=None,
        expiry_date=None,
    )


@pytest.mark.asyncio
async def test_v2_order_full_chain(client: AsyncClient, db_session_like_pg: AsyncSession):
    """
    Phase 5+ 下的“订单驱动履约链”核心验收（当前主线）：

    1) ingest：创建订单并写 trace_id
    2) 人工履约决策：调用 manual-assign 指定执行仓，并标记可进入履约
    3) 入库（为后续 pick/ship 准备库存）
    4) pick → ship_commit
    5) debug trace：至少出现 ORDER_CREATED + SHIPMENT/SHIP_COMMIT
    """
    plat = "PDD"
    shop_id = "1"
    uniq = uuid4().hex[:10]
    ext = f"ORD-TEST-3001-{uniq}"
    order_ref = f"ORD:{plat}:{shop_id}:{ext}"
    now = datetime.now(timezone.utc)

    province = "UT-PROV"
    await _ensure_store_route_to_wh1(db_session_like_pg, plat=plat, shop_id=shop_id, province=province)
    await db_session_like_pg.commit()

    trace_id = f"TEST-TRACE-ORDER-3001-{uniq}"

    print(f"[TEST] 准备订单 {order_ref}")

    # 1) 创建订单（必须带 province）
    r = await OrderService.ingest(
        db_session_like_pg,
        platform=plat,
        shop_id=shop_id,
        ext_order_no=ext,
        occurred_at=now,
        buyer_name="tester",
        buyer_phone="",
        order_amount=0,
        pay_amount=0,
        items=[{"item_id": 3001, "qty": 1, "title": "猫粮"}],
        address={"province": province, "receiver_name": "X", "receiver_phone": "000"},
        extras=None,
        trace_id=trace_id,
    )
    await db_session_like_pg.commit()
    print(f"[TEST] ingest 返回: {r}")
    assert r["ref"] == order_ref

    # 2) manual-assign（需要登录；测试环境一般用 admin/admin123）
    login = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"/orders/{plat}/{shop_id}/{ext}/fulfillment/manual-assign",
        json={"warehouse_id": 1, "reason": "UT assign", "note": "test"},
        headers=headers,
    )
    print("[HTTP] manual-assign status:", resp.status_code, "body:", resp.text)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "OK"
    assert body["ref"] == order_ref
    assert int(body["to_warehouse_id"]) == 1

    # 3) 入库（Lot-World：必须锚定 lot_id）
    stock_svc = StockService()
    lot_code = "BATCH-001"
    lot_id = await _ensure_supplier_lot(db_session_like_pg, wh_id=1, item_id=3001, lot_code=lot_code)

    await stock_svc.adjust_lot(
        session=db_session_like_pg,
        item_id=3001,
        warehouse_id=1,
        lot_id=int(lot_id),
        delta=10,
        reason="RECEIPT",
        ref=f"UNIT-TEST-IN-3001-{uniq}",
        ref_line=1,
        occurred_at=now,
        batch_code=lot_code,
        production_date=now.date(),
        expiry_date=None,
        trace_id=None,
    )
    await db_session_like_pg.commit()
    print("[TEST] 已通过 StockService.adjust_lot 入库 10 件到 BATCH-001")

    # 4) pick（终态合同：batch_code 必须按行提供）
    resp = await client.post(
        f"/orders/{plat}/{shop_id}/{ext}/pick",
        json={
            "warehouse_id": 1,
            "lines": [{"item_id": 3001, "qty": 1, "batch_code": "BATCH-001"}],
        },
    )
    print("[HTTP] pick status:", resp.status_code, "body:", resp.text)
    assert resp.status_code == 200, resp.text
    pick_list = resp.json()
    assert isinstance(pick_list, list)
    assert len(pick_list) == 1

    # 5) ship
    resp = await client.post(
        f"/orders/{plat}/{shop_id}/{ext}/ship",
        json={
            "warehouse_id": 1,
            "lines": [{"item_id": 3001, "qty": 1}],
        },
    )
    print("[HTTP] ship status:", resp.status_code, "body:", resp.text)
    assert resp.status_code == 200, resp.text
    ship_data = resp.json()
    assert ship_data["ref"] == order_ref
    assert ship_data["event"] == "SHIP_COMMIT"
    assert ship_data["status"] in ("OK", "IDEMPOTENT")

    # 6) dev/orders
    resp = await client.get(f"/dev/orders/{plat}/{shop_id}/{ext}")
    assert resp.status_code == 200, resp.text
    ov = resp.json()
    print("[HTTP] dev/orders 返回:", json.dumps(ov, ensure_ascii=False))
    trace_id2 = ov.get("trace_id") or ov["order"]["trace_id"]
    assert trace_id2

    # 7) trace
    resp = await client.get(f"/debug/trace/{trace_id2}")
    print("[HTTP] /debug/trace status:", resp.status_code)
    assert resp.status_code == 200, resp.text
    trace = resp.json()
    events = trace["events"]
    kinds = [e["kind"] for e in events]
    summaries = [e["summary"] for e in events]

    assert any("ORDER_CREATED" in s for s in summaries), summaries
    assert any(k == "SHIPMENT" for k in kinds), kinds
    assert any("SHIP_COMMIT" in s for s in summaries), summaries
