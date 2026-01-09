# tests/api/test_v2_full_chain.py
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_service import OrderService
from app.services.stock_service import StockService


@pytest.mark.asyncio
async def test_v2_order_full_chain(client: AsyncClient, db_session_like_pg: AsyncSession):
    """
    订单驱动 v2 履约链测试（核心验收）：

    ORDER_CREATED → RESERVE_APPLIED → PICK(ledger) → SHIP_COMMIT → trace 聚合
    """

    plat = "PDD"
    shop_id = "1"
    ext = "ORD-TEST-3001"
    order_ref = f"ORD:{plat}:{shop_id}:{ext}"
    now = datetime.now(timezone.utc)

    print(f"[TEST] 准备订单 {order_ref}")

    # 1) 创建订单
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
        address=None,
        extras=None,
        trace_id="TEST-TRACE-ORDER-3001",
    )
    await db_session_like_pg.commit()
    order_id = r["id"]
    print(f"[TEST] ingest 返回: {r}")

    # 2) 补 warehouse_id
    await db_session_like_pg.execute(
        text("UPDATE orders SET warehouse_id = 1 WHERE id = :oid"),
        {"oid": order_id},
    )
    await db_session_like_pg.commit()
    print(f"[TEST] 已补 orders.id={order_id} 的 warehouse_id=1")

    rows = (
        (
            await db_session_like_pg.execute(
                text(
                    """
                SELECT id, platform, shop_id, ext_order_no, warehouse_id, trace_id
                  FROM orders
                 WHERE platform = :p AND shop_id = :s AND ext_order_no = :o
                """
                ),
                {"p": plat, "s": shop_id, "o": ext},
            )
        )
        .mappings()
        .all()
    )
    print("[TEST] 当前 orders 行:", rows)

    # 3) reserve
    resp = await client.post(
        f"/orders/{plat}/{shop_id}/{ext}/reserve",
        json={"lines": [{"item_id": 3001, "qty": 1}]},
    )
    print("[HTTP] reserve status:", resp.status_code, "body:", resp.text)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "OK"
    assert data["ref"] == order_ref
    assert data["reservation_id"] is not None
    assert data["lines"] == 1

    # 4) 入库
    stock_svc = StockService()
    await stock_svc.adjust(
        session=db_session_like_pg,
        item_id=3001,
        delta=10,
        reason="RECEIPT",
        ref="UNIT-TEST-IN-3001",
        ref_line=1,
        occurred_at=now,
        batch_code="BATCH-001",
        production_date=now.date(),
        warehouse_id=1,
        trace_id=None,
    )
    await db_session_like_pg.commit()
    print("[TEST] 已通过 StockService.adjust 入库 10 件到 BATCH-001")

    # 5) pick
    resp = await client.post(
        f"/orders/{plat}/{shop_id}/{ext}/pick",
        json={
            "warehouse_id": 1,
            "batch_code": "BATCH-001",
            "lines": [{"item_id": 3001, "qty": 1}],
        },
    )
    print("[HTTP] pick status:", resp.status_code, "body:", resp.text)
    assert resp.status_code == 200, resp.text
    pick_list = resp.json()
    assert isinstance(pick_list, list)
    assert len(pick_list) == 1
    pick_rec = pick_list[0]
    assert pick_rec["item_id"] == 3001
    assert pick_rec["warehouse_id"] == 1
    assert pick_rec["batch_code"] == "BATCH-001"
    assert pick_rec["picked"] == 1
    assert pick_rec["status"] in ("OK", "IDEMPOTENT")

    # 6) ship
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

    # 7) dev/orders
    resp = await client.get(f"/dev/orders/{plat}/{shop_id}/{ext}")
    assert resp.status_code == 200, resp.text
    ov = resp.json()
    print("[HTTP] dev/orders 返回:", json.dumps(ov, ensure_ascii=False))
    trace_id = ov.get("trace_id") or ov["order"]["trace_id"]
    assert trace_id
    print("[TEST] dev/orders trace_id:", trace_id)

    # 8) ledger rows
    res = await db_session_like_pg.execute(
        text(
            """
            SELECT id, reason, ref, ref_line, item_id, warehouse_id, batch_code, delta, after_qty, trace_id
              FROM stock_ledger
             WHERE ref = :ref
             ORDER BY id
            """
        ),
        {"ref": order_ref},
    )
    ledger_rows = res.mappings().all()
    print("[TEST] stock_ledger rows for ref", order_ref, ":", ledger_rows)

    # 9) trace
    resp = await client.get(f"/debug/trace/{trace_id}")
    print("[HTTP] /debug/trace status:", resp.status_code)
    assert resp.status_code == 200, resp.text
    trace = resp.json()
    events = trace["events"]
    kinds = [e["kind"] for e in events]
    summaries = [e["summary"] for e in events]

    print("[TEST] trace kinds:", kinds)
    print("[TEST] trace summaries:")
    for e in events:
        print("  -", e["ts"], e["source"], e["kind"], "=>", e["summary"])

    # ORDER_CREATED 审计事件
    assert any("ORDER_CREATED" in s for s in summaries), summaries

    # reservation 事件（头或行）
    assert any(k.startswith("reservation_") or k == "reservation_line" for k in kinds), kinds

    # ledger 事件（订单出库应落为 SHIPMENT）
    assert any(k == "SHIPMENT" for k in kinds), kinds

    # SHIP_COMMIT 审计事件
    assert any("SHIP_COMMIT" in s for s in summaries), summaries


@pytest.mark.asyncio
async def test_v2_order_reserve_requires_warehouse(
    client: AsyncClient, db_session_like_pg: AsyncSession
):
    """
    没有 warehouse_id 的订单，调用订单驱动预占时应失败，
    防止“未定仓预占”。
    """
    plat = "PDD"
    shop_id = "1"
    ext = "ORD-NO-WH"
    now = datetime.now(timezone.utc)

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
        items=[{"item_id": 3002, "qty": 1, "title": "测试品"}],
        address=None,
        extras=None,
        trace_id="TEST-TRACE-NO-WH",
    )
    await db_session_like_pg.commit()

    resp = await client.post(
        f"/orders/{plat}/{shop_id}/{ext}/reserve",
        json={"lines": [{"item_id": 3002, "qty": 1}]},
    )
    print("[HTTP] reserve(no-wh) status:", resp.status_code, "body:", resp.text)
    assert resp.status_code in (400, 409, 422, 500)
    body = resp.json()
    assert "warehouse_id" in json.dumps(body) or "insufficient" in json.dumps(body)
